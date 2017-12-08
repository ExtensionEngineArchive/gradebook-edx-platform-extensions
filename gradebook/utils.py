"""
Utils methods for gradebook app
"""
import json

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import transaction
from django.utils.decorators import method_decorator

from course_blocks.api import get_course_blocks
from courseware import grades
from courseware.access import is_staff_or_instructor_on_course
from courseware.courses import get_course, get_course_with_access
from gradebook.models import StudentGradebook
from instructor.offline_gradecalc import student_grades
from instructor.views.gradebook_api import get_letter_grade, manual_grading_xblock_patcher
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore import EdxJSONEncoder
from xmodule.modulestore.django import modulestore


@method_decorator(transaction.non_atomic_requests)
def generate_user_gradebook(course_key, user):
    """
    Recalculates the specified user's gradebook entry
    """
    with modulestore().bulk_operations(course_key):
        course_descriptor = get_course(course_key, depth=None)
        course_structure = get_course_blocks(user, course_descriptor.location)
        grade_summary = grades.grade(user, course_descriptor, course_structure)
        grading_policy = course_descriptor.grading_policy
        progress_summary = grades.progress_summary(user, course_descriptor, course_structure)
        grade = grade_summary['percent']
        proforma_grade = grades.calculate_proforma_grade(grade_summary, grading_policy)

    progress_summary = get_json_data(progress_summary)
    grade_summary = get_json_data(grade_summary)
    grading_policy = get_json_data(grading_policy)

    gradebook_entry, created = StudentGradebook.objects.get_or_create(
        user=user, course_id=course_key, defaults={
                'grade': grade,
                'proforma_grade': proforma_grade,
                'progress_summary': progress_summary,
                'grade_summary': grade_summary,
                'grading_policy': grading_policy
            }
    )

    if gradebook_entry.grade != grade:
        gradebook_entry.grade = grade
        gradebook_entry.proforma_grade = proforma_grade
        gradebook_entry.progress_summary = progress_summary
        gradebook_entry.grade_summary = grade_summary
        gradebook_entry.grading_policy = grading_policy
        gradebook_entry.save()

    return gradebook_entry


def get_json_data(obj):
    try:
        json_data = json.dumps(obj, cls=EdxJSONEncoder)
    except:
        json_data = {}
    return json_data


def get_ordered_grades(course):
    return sorted(course.grade_cutoffs.items(), key=lambda i: i[1], reverse=True)


def get_course_sections(courseware_summary):
    graded_sections = {}

    for chapter in courseware_summary:
        chapter_name = chapter['display_name']

        for section in chapter['sections']:
            if len(section['scores']) > 0 and section['graded']:
                for score in section['scores']:
                    graded_sections[score.module_id.block_id] = {
                        'chapter_name': chapter_name,
                        'possible_score': score.possible,
                    }
                graded_sections[section['url_name']] = {
                    'chapter_name': chapter_name,
                    'possible_score': section['section_total'].possible,
                }

    return graded_sections


def get_enrolled_non_staff_students(course, course_key):
    students = User.objects.filter(
        courseenrollment__course_id=course_key,
        courseenrollment__is_active=1
    ).order_by('username').select_related('profile')

    return [student for student in students if not is_staff_or_instructor_on_course(student, course)]


def get_params_for_grade_summaries(user, course_id):
    course_key = CourseKey.from_string(course_id)
    course = get_course_with_access(user, 'staff', course_key, depth=None)
    course_structure = get_course_blocks(user, course.location)
    courseware_summary = grades.progress_summary(user, course, course_structure, extended_data=True)

    return {
        'course': course,
        'course_structure': course_structure,
        'graded_sections': get_course_sections(courseware_summary),
        'non_staff_students': get_enrolled_non_staff_students(course, course_key),
    }


def get_grade_summaries(request, students, course, course_structure, graded_sections):
    with modulestore().bulk_operations(course.location.course_key):
        student_info = []
        len_of_modules = 0
        greatest_student_index = None

        for index, student in enumerate(students):
            course_id = course.id.to_deprecated_string()
            gradebook_entry = {
                'username': student.username,
                'full_name': student.get_full_name(),
                'user_id': student.id,
                'email': student.email,
                'course_id': course_id,
                'progress_page_url': reverse(
                    'student_progress',
                    kwargs=dict(course_id=course_id, student_id=student.id)
                ),
                # NDPD-631, NDPD-641: Pass the graded_sections here, again via an optional parameter
                'grade_summary': student_grades(
                    student,
                    request,
                    course,
                    course_structure=course_structure,
                    graded_sections=graded_sections,
                    keep_raw_scores=True
                ),
            }

            if len_of_modules < gradebook_entry['grade_summary']['manual_graded_total_count']:
                len_of_modules = gradebook_entry['grade_summary']['manual_graded_total_count']
                greatest_student_index = index

            student_info.append(gradebook_entry)

        if greatest_student_index > 0 and len_of_modules > 0:
            student_info.insert(0, student_info.pop(greatest_student_index))

        student_info = manual_grading_xblock_patcher(student_info, greatest_student_index, len_of_modules)
    return student_info


def get_updated_grade_summaries(request, students, course, course_structure, graded_sections):
    grade_summaries = get_grade_summaries(
        request,
        students,
        course,
        course_structure,
        graded_sections,
    )
    ordered_grades = get_ordered_grades(course)
    update_grade_summaries(grade_summaries, ordered_grades)
    return grade_summaries


def update_grade_summaries(grade_summaries, ordered_grades):
    for student_summary in grade_summaries:
        grade_summary = student_summary['grade_summary']
        grade_summary.update({
            'current_letter_grade': get_letter_grade(grade_summary['current_percent'], ordered_grades),
            'total_letter_grade': get_letter_grade(grade_summary['percent'], ordered_grades),
        })

        for section in grade_summary['section_breakdown']:
            letter_grade = None
            percent = section['percent']

            if type(percent) is unicode:
                displayed_value = percent
            else:
                displayed_value = section.get('displayed_value') or '{0:.2f}%'.format(100 * percent)

                if type(percent) is float and percent > 0:
                    letter_grade = get_letter_grade(percent, ordered_grades)

            # TODO: Move to grades.py
            if '=' in section['detail']:
                # Examples:
                # Weekly Problems Average = 0%
                # Exam 2 = 0%
                # Represents a score of an entire graded category (e.g. Weekly Problems or Exam 2)
                scores = grade_summary['totaled_scores'].get(section['category'], [])
                score_earned = 0
                score_possible = 0
                for score in scores:
                    score_earned += score.earned
                    score_possible += score.possible
            elif '-' in section['detail']:
                # Example: Weekly Homework 14 Unreleased - 0% (?/?)
                # Represents a score for a graded assessment within a section
                score_from_label = section['detail'].split(' ')[-1]
                score_earned = score_from_label.split('(')[1].split('/')[0]
                score_possible = score_from_label.split(')')[0].split('/')[1]
            else:
                score_earned = section.get('score_earned', 0)
                score_possible = section.get('score_possible', 0)

            try:
                grade_description = '({:0.2f}/{:0.2f})'.format(float(score_earned), float(score_possible))
            except:
                grade_description = '({}/{})'.format(score_earned, score_possible)

            section.update({
                'displayed_value': displayed_value,
                'grade_description': grade_description,
                'letter_grade': letter_grade,
                'score_earned': score_earned,
                'score_possible': score_possible,
            })

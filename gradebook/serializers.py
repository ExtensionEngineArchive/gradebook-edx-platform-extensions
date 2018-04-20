""" Django REST Framework Serializers """
from openedx.core.lib.courses import course_image_url

from rest_framework import serializers
from rest_framework.reverse import reverse

from instructor.views import gradebook_api
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


class ScoreSerializer(serializers.Serializer):
    auto_grade = serializers.SerializerMethodField()
    earned = serializers.FloatField()
    graded = serializers.BooleanField()
    module_id = serializers.SerializerMethodField()
    possible = serializers.FloatField()
    section = serializers.CharField()

    def get_auto_grade(self, data):
        return getattr(data, 'auto_grade', None)

    def get_module_id(self, data):
        return str(data.module_id)


class SectionBreakdownSerializer(serializers.Serializer):
    are_grades_published = serializers.SerializerMethodField()
    auto_grade = serializers.SerializerMethodField()
    category = serializers.CharField()
    chapter_name = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()
    detail = serializers.CharField()
    displayed_value = serializers.CharField()
    grade_description = serializers.SerializerMethodField()
    is_ag = serializers.SerializerMethodField()
    is_average = serializers.SerializerMethodField()
    is_manually_graded = serializers.SerializerMethodField()
    label = serializers.CharField()
    letter_grade = serializers.SerializerMethodField()
    module_id = serializers.SerializerMethodField()
    percent = serializers.CharField()
    score_earned = serializers.CharField()
    score_possible = serializers.CharField()
    section_block_id = serializers.SerializerMethodField()
    subsection_name = serializers.SerializerMethodField()

    def get_are_grades_published(self, data):
        if self.get_is_manually_graded(data):
            return data.get('are_grades_published', False)
        return True

    def get_auto_grade(self, data):
        auto_grade = data.get('auto_grade')
        if auto_grade:
            return '{earned}/{possible}'.format(earned=auto_grade.earned, possible=auto_grade.possible)
        return None

    def get_chapter_name(self, data):
        return data.get('chapter_name', '')

    def get_comment(self, data):
        return data.get('comment', '')

    def get_grade_description(self, data):
        score_earned = data.get('score_earned')
        score_possible = data.get('score_possible')

        try:
            return '({:0.2f}/{:0.2f})'.format(float(score_earned), float(score_possible))
        except ValueError:
            return '({}/{})'.format(score_earned, score_possible)

    def get_is_ag(self, data):
        return data.get('is_ag', False)

    def get_is_average(self, data):
        return data.get('is_average', False)

    def get_is_manually_graded(self, data):
        return data.get('is_manually_graded', False)

    def get_letter_grade(self, data):
        percent = data.get('percent')
        if type(percent) is float and percent > 0:
            return gradebook_api.get_letter_grade(percent, self.context.get('course_grades'))
        return None

    def get_module_id(self, data):
        return str(data.get('block_id', ''))

    def get_section_block_id(self, data):
        return data.get('section_block_id', '')

    def get_subsection_name(self, data):
        return data.get('subsection_name', '')


class GradeSummarySerializer(serializers.Serializer):
    """ Serializer for student grade summary """
    current_letter_grade = serializers.SerializerMethodField()
    current_percent = serializers.CharField()
    grade = serializers.CharField()
    grade_breakdown = serializers.ListField()
    percent = serializers.CharField()
    section_breakdown = serializers.SerializerMethodField()
    total_letter_grade = serializers.SerializerMethodField()

    def get_current_letter_grade(self, data):
        return gradebook_api.get_letter_grade(data.get('current_percent'), self.context.get('course_grades'))

    def get_section_breakdown(self, data):
        return SectionBreakdownSerializer(
            data.get('section_breakdown'),
            context={'course_grades': self.context.get('course_grades')},
            many=True
        ).data

    def get_total_letter_grade(self, data):
        return gradebook_api.get_letter_grade(data.get('percent'), self.context.get('course_grades'))


class StudentGradebookEntrySerializer(serializers.Serializer):
    """ Serializer for student gradebook entry """
    course_id = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    grade_summary = serializers.SerializerMethodField()
    progress_page_url = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()

    def get_grade_summary(self, data):
        return GradeSummarySerializer(
            data.get('grade_summary'),
            context={'course_grades': self.context.get('course_grades')}
        ).data

""" API implementation for course-oriented interactions. """

import logging

from django.core.urlresolvers import reverse
from django.db import transaction
from opaque_keys.edx.keys import CourseKey
from rest_framework import generics

from courseware.access import get_enrolled_non_staff_students
from courseware.courses import get_course_with_access
from instructor.offline_gradecalc import student_grades
from instructor.views.gradebook_api import get_letter_grade, manual_grading_xblock_patcher
from xmodule.modulestore.django import modulestore

from gradebook.pagination import GradebookPagination
from gradebook.serializers import StudentGradebookEntrySerializer

log = logging.getLogger(__name__)


# NDPD-737: Platform cleanup
class CourseGradeBook(generics.ListAPIView):
    """
    View to list the grade summary of all users enrolled in the course.
    """
    pagination_class = GradebookPagination

    @transaction.non_atomic_requests
    def dispatch(self, request, *args, **kwargs):
        return super(CourseGradeBook, self).dispatch(request, *args, **kwargs)

    def list(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(request.user, 'staff', course_key, depth=None)
        non_staff_students = get_enrolled_non_staff_students(course, course_key)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(non_staff_students, request)

        grade_summaries = prepare_gradebook(course, page, request.user)

        serializer = StudentGradebookEntrySerializer(grade_summaries, many=True)

        return paginator.get_paginated_response(serializer.data)

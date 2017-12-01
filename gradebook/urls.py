"""
Gradebook API URI specification
"""
from django.conf import settings
from django.conf.urls import patterns, url
from rest_framework.urlpatterns import format_suffix_patterns

import gradebook.views as courses_views

COURSE_ID_PATTERN = settings.COURSE_ID_PATTERN

urlpatterns = patterns(
    '',
    url(
        r'^{}/gradebook/*$'.format(COURSE_ID_PATTERN), 
        courses_views.CourseGradeBook.as_view(), 
        name='course-gradebook'
    ),
)

urlpatterns = format_suffix_patterns(urlpatterns)

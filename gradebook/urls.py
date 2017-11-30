"""
Gradebook API URI specification
"""
from django.conf import settings
from django.conf.urls import patterns, url

from rest_framework.urlpatterns import format_suffix_patterns

import gradebook.views as courses_views

COURSE_ID_PATTERN = settings.COURSE_ID_PATTERN
USERNAME_PATTERN = settings.USERNAME_PATTERN

urlpatterns = patterns(
    '',
    url(r'^{}/gradebook/*$'.format(COURSE_ID_PATTERN), courses_views.CourseGradeBook.as_view(), name='course-gradebook'),
    url(r'^{}/metrics/*$'.format(COURSE_ID_PATTERN), courses_views.CoursesMetrics.as_view(), name='course-metrics'),
    url(r'^{}/user-metrics/{}$'.format(COURSE_ID_PATTERN, USERNAME_PATTERN),
        courses_views.CoursesUserMetrics.as_view(), name='course-user-metrics'),
    url(r'^{}/time-series-metrics/*$'.format(COURSE_ID_PATTERN),
        courses_views.CoursesTimeSeriesMetrics.as_view(), name='course-time-series-metrics'),
    url(r'^{}/metrics/grades/*$'.format(COURSE_ID_PATTERN), courses_views.CoursesMetricsGradesList.as_view()),
    url(r'^{}/metrics/grades/leaders/*$'.format(COURSE_ID_PATTERN),
        courses_views.CoursesMetricsGradesLeadersList.as_view(), name='course-metrics-grades-leaders'),
)

urlpatterns = format_suffix_patterns(urlpatterns)

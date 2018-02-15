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
)

urlpatterns = format_suffix_patterns(urlpatterns)

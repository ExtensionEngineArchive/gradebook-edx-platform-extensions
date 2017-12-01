""" Django REST Framework Serializers """
from openedx.core.lib.courses import course_image_url

from rest_framework import serializers
from rest_framework.reverse import reverse

from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


class ScoreSerializer(serializers.Serializer):
    earned = serializers.FloatField()
    graded = serializers.BooleanField()
    module_id = serializers.SerializerMethodField()
    possible = serializers.FloatField()
    section = serializers.CharField()

    def get_module_id(self, data):
        return str(data.module_id)


class SectionBreakdownSerializer(serializers.Serializer):
    category = serializers.CharField()
    chapter_name = serializers.SerializerMethodField()
    detail = serializers.CharField()
    displayed_value = serializers.CharField()
    grade_description = serializers.CharField()
    label = serializers.CharField()
    letter_grade = serializers.CharField()
    module_id = serializers.SerializerMethodField()
    percent = serializers.CharField()
    score_earned = serializers.CharField()
    score_possible = serializers.CharField()

    def get_chapter_name(self, data):
        return data.get('chapter_name', '')

    def get_module_id(self, data):
        return str(data.get('module_id', ''))


class GradeSummarySerializer(serializers.Serializer):
    """ Serializer for student grade summary """
    current_letter_grade = serializers.CharField()
    current_percent = serializers.CharField()
    grade = serializers.IntegerField()
    grade_breakdown = serializers.ListField()
    manual_graded_per_policy = serializers.ListField()
    manual_graded_total_count = serializers.IntegerField()
    percent = serializers.CharField()
    raw_scores = ScoreSerializer(many=True)
    section_breakdown = SectionBreakdownSerializer(many=True)
    total_letter_grade = serializers.CharField()
    totaled_scores = serializers.SerializerMethodField()

    def get_totaled_scores(self, data):
        for section in data['totaled_scores']:
            yield {
                section: ScoreSerializer(data['totaled_scores'][section], many=True).data
            }


class StudentGradebookEntrySerializer(serializers.Serializer):
    """ Serializer for student gradebook entry """
    email = serializers.CharField()
    full_name = serializers.CharField()
    grade_summary = GradeSummarySerializer()
    user_id = serializers.IntegerField()
    username = serializers.CharField()

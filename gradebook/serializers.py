""" Django REST Framework Serializers """
from openedx.core.lib.courses import course_image_url

from rest_framework import serializers
from rest_framework.reverse import reverse

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
    grade_description = serializers.CharField()
    is_average = serializers.SerializerMethodField()
    is_manually_graded = serializers.SerializerMethodField()
    label = serializers.CharField()
    letter_grade = serializers.CharField()
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
        return data.get('auto_grade')

    def get_chapter_name(self, data):
        return data.get('chapter_name', '')

    def get_comment(self, data):
        return data.get('comment', '')

    def get_is_average(self, data):
        return data.get('is_average', False)

    def get_is_manually_graded(self, data):
        return data.get('is_manually_graded', False)

    def get_module_id(self, data):
        return str(data.get('module_id', data.get('block_id', '')))

    def get_section_block_id(self, data):
        return data.get('section_block_id', '')

    def get_subsection_name(self, data):
        return data.get('subsection_name', '')


class GradeSummarySerializer(serializers.Serializer):
    """ Serializer for student grade summary """
    current_letter_grade = serializers.CharField()
    current_percent = serializers.CharField()
    grade = serializers.CharField()
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
    course_id = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    grade_summary = GradeSummarySerializer()
    progress_page_url = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()

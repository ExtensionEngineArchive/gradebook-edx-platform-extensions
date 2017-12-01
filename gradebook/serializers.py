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


class GradeSerializer(serializers.Serializer):
    """ Serializer for model interactions """
    grade = serializers.FloatField()


class CourseLeadersSerializer(serializers.Serializer):
    """ Serializer for course leaderboard """
    id = serializers.IntegerField(source='user__id')  # pylint: disable=invalid-name
    username = serializers.CharField(source='user__username')
    # Percentage grade (versus letter grade)
    grade = serializers.FloatField()
    recorded = serializers.DateTimeField(source='modified')


class CourseSocialLeadersSerializer(serializers.Serializer):
    """ Serializer for course leaderboard """
    id = serializers.IntegerField(source='user__id')  # pylint: disable=invalid-name
    username = serializers.CharField(source='user__username')
    score = serializers.IntegerField()
    recorded = serializers.DateTimeField(source='modified')


class CourseCompletionsLeadersSerializer(serializers.Serializer):
    """ Serializer for course completions leaderboard """
    id = serializers.IntegerField(source='user__id')  # pylint: disable=invalid-name
    username = serializers.CharField(source='user__username')
    completions = serializers.SerializerMethodField('get_completion_percentage')

    def get_completion_percentage(self, obj):
        """
        formats get completions as percentage
        """
        total_completions = self.context['total_completions'] or 0
        completions = obj['completions'] or 0
        completion_percentage = 0
        if total_completions > 0:
            completion_percentage = min(100 * (completions / float(total_completions)), 100)
        return completion_percentage


class CourseSerializer(serializers.Serializer):
    """ Serializer for Courses """
    id = serializers.CharField()  # pylint: disable=invalid-name
    name = serializers.CharField(source='display_name')
    category = serializers.SerializerMethodField()
    number = serializers.CharField(source='display_number_with_default')
    org = serializers.CharField(source='display_org_with_default')
    uri = serializers.SerializerMethodField()
    course_image_url = serializers.SerializerMethodField()
    due = serializers.SerializerMethodField('get_due_date')
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()

    def get_uri(self, course):
        """
        Builds course detail uri
        """
        return reverse('course-detail', args=[course.id], request=self.context.get('request'))

    def get_course_image_url(self, course):
        """
        Builds course image url
        """
        return course.course_image_url if isinstance(course, CourseOverview) else course_image_url(course)

    def get_category(self, course):
        """
        category: The type of content. In this case, the value is always "course".
        """
        return 'course'

    def get_due_date(self, course):
        """
        due:  The due date. For courses, the value is always null.
        """
        return None


class OrganizationCourseSerializer(CourseSerializer):
    """ Serializer for Organization Courses """
    name = serializers.CharField(source='display_name')
    enrolled_users = serializers.ListField(child=serializers.IntegerField())

    class Meta(object):
        """ Serializer/field specification """
        fields = ('id', 'name', 'number', 'org', 'start', 'end', 'due', 'enrolled_users', )
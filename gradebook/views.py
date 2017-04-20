""" API implementation for course-oriented interactions. """

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Min
from django.utils.translation import ugettext_lazy as _
from django.db.models import F

from rest_framework import status
from rest_framework.response import Response

from courseware.models import StudentModule
from progress.models import StudentProgress, CourseModuleCompletion
from student.models import CourseEnrollment
from student.roles import get_aggregate_exclusion_user_ids

from gradebook.models import StudentGradebook
from gradebook.courseware_access import get_course, get_course_key, course_exists
from gradebook.permissions import SecureAPIView, SecureListAPIView
from gradebook.api_utils import (
    generate_base_uri,
    get_time_series_data,
    parse_datetime,
    get_ids_from_list_param,
    css_param_to_list,
)
from gradebook.serializers import GradeSerializer, CourseLeadersSerializer


log = logging.getLogger(__name__)


class CoursesMetricsGradesList(SecureListAPIView):
    """
    ### The CoursesMetricsGradesList view allows clients to retrieve a list of grades for the specified Course
    - URI: ```/api/courses/{course_id}/grades/```
    - GET: Returns a JSON representation (array) of the set of grade objects
    ### Use Cases/Notes:
    * Example: Display a graph of all of the grades awarded for a given course
    """

    def get(self, request, course_id):  # pylint: disable=W0221
        """
        GET /api/courses/{course_id}/metrics/grades?user_ids=1,2
        """
        if not course_exists(request, request.user, course_id):
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        course_key = get_course_key(course_id)
        exclude_users = get_aggregate_exclusion_user_ids(course_key)
        queryset = StudentGradebook.objects.filter(course_id__exact=course_key,
                                                   user__is_active=True,
                                                   user__courseenrollment__is_active=True,
                                                   user__courseenrollment__course_id__exact=course_key)\
            .exclude(user__in=exclude_users)
        user_ids = get_ids_from_list_param(self.request, 'user_id')
        if user_ids:
            queryset = queryset.filter(user__in=user_ids)

        group_ids = get_ids_from_list_param(self.request, 'groups')
        if group_ids:
            queryset = queryset.filter(user__groups__in=group_ids).distinct()

        sum_of_grades = sum([gradebook.grade for gradebook in queryset])
        queryset_grade_avg = sum_of_grades / len(queryset) if len(queryset) > 0 else 0
        queryset_grade_count = len(queryset)
        queryset_grade_max = queryset.aggregate(Max('grade'))
        queryset_grade_min = queryset.aggregate(Min('grade'))

        course_metrics = StudentGradebook.generate_leaderboard(course_key,
                                                               group_ids=group_ids,
                                                               exclude_users=exclude_users)

        response_data = {}
        base_uri = generate_base_uri(request)
        response_data['uri'] = base_uri

        response_data['grade_average'] = queryset_grade_avg
        response_data['grade_count'] = queryset_grade_count
        response_data['grade_maximum'] = queryset_grade_max['grade__max']
        response_data['grade_minimum'] = queryset_grade_min['grade__min']

        response_data['course_grade_average'] = course_metrics['course_avg']
        response_data['course_grade_maximum'] = course_metrics['course_max']
        response_data['course_grade_minimum'] = course_metrics['course_min']
        response_data['course_grade_count'] = course_metrics['course_count']

        response_data['grades'] = []
        for row in queryset:
            serializer = GradeSerializer(row)
            response_data['grades'].append(serializer.data)  # pylint: disable=E1101
        return Response(response_data, status=status.HTTP_200_OK)


class CoursesMetrics(SecureAPIView):
    """
    ### The CoursesMetrics view allows clients to retrieve a list of Metrics for the specified Course
    - URI: ```/api/courses/{course_id}/metrics/?organization={organization_id}```
    - GET: Returns a JSON representation (array) of the set of course metrics
    - metrics can be filtered by organization by adding organization parameter to GET request
    - metrics_required param should be comma separated list of metrics required
    - possible values for metrics_required param are
    - ``` users_started,modules_completed,users_completed,thread_stats ```
    ### Use Cases/Notes:
    * Example: Display number of users enrolled in a given course
    """

    def get(self, request, course_id):  # pylint: disable=W0613
        """
        GET /api/courses/{course_id}/metrics/
        """
        if not course_exists(request, request.user, course_id):
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        course_descriptor, course_key, course_content = get_course(request, request.user, course_id)  # pylint: disable=W0612
        exclude_users = get_aggregate_exclusion_user_ids(course_key)
        users_enrolled_qs = CourseEnrollment.objects.users_enrolled_in(course_key).exclude(id__in=exclude_users)
        organization = request.query_params.get('organization', None)
        metrics_required = css_param_to_list(request, 'metrics_required')
        org_ids = None
        if organization:
            users_enrolled_qs = users_enrolled_qs.filter(organizations=organization)
            org_ids = [organization]

        group_ids = get_ids_from_list_param(self.request, 'groups')
        if group_ids:
            users_enrolled_qs = users_enrolled_qs.filter(groups__in=group_ids)

        data = {
            'grade_cutoffs': course_descriptor.grading_policy['GRADE_CUTOFFS'],
            'users_enrolled': users_enrolled_qs.distinct().count()
        }

        if 'users_started' in metrics_required:
            users_started = StudentProgress.get_num_users_started(
                course_key,
                exclude_users=exclude_users,
                org_ids=org_ids,
                group_ids=group_ids
            )
            data['users_started'] = users_started
            data['users_not_started'] = data['users_enrolled'] - users_started

        if 'modules_completed' in metrics_required:
            modules_completed = StudentProgress.get_total_completions(
                course_key, exclude_users=exclude_users, org_ids=org_ids, group_ids=group_ids
            )
            data['modules_completed'] = modules_completed

        if 'users_completed' in metrics_required:
            users_completed = StudentGradebook.get_num_users_completed(
                course_key, exclude_users=exclude_users, org_ids=org_ids, group_ids=group_ids
            )
            data['users_completed'] = users_completed

        return Response(data, status=status.HTTP_200_OK)


class CoursesTimeSeriesMetrics(SecureAPIView):
    """
    ### The CoursesTimeSeriesMetrics view allows clients to retrieve a list of Metrics for the specified Course
    in time series format.
    - URI: ```/api/courses/{course_id}/time-series-metrics/?start_date={date}&end_date={date}
        &interval={interval}&organization={organization_id}```
    - interval can be `days`, `weeks` or `months`
    - GET: Returns a JSON representation with three metrics
    {
        "users_not_started": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]],
        "users_started": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]],
        "users_completed": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]],
        "modules_completed": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]]
        "users_enrolled": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]]
        "active_users": [[datetime-1, count-1], [datetime-2, count-2], ........ [datetime-n, count-n]]
    }
    - metrics can be filtered by organization by adding organization parameter to GET request
    ### Use Cases/Notes:
    * Example: Display number of users completed, started or not started in a given course for a given time period
    """

    def get(self, request, course_id):  # pylint: disable=W0613
        """
        GET /api/courses/{course_id}/time-series-metrics/
        """
        if not course_exists(request, request.user, course_id):
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        start = request.query_params.get('start_date', None)
        end = request.query_params.get('end_date', None)
        interval = request.query_params.get('interval', 'days')
        if not start or not end:
            return Response({"message": _("Both start_date and end_date parameters are required")},
                            status=status.HTTP_400_BAD_REQUEST)
        if interval not in ['days', 'weeks', 'months']:
            return Response({"message": _("Interval parameter is not valid. It should be one of these "
                                          "'days', 'weeks', 'months'")}, status=status.HTTP_400_BAD_REQUEST)
        start_dt = parse_datetime(start)
        end_dt = parse_datetime(end)
        course_key = get_course_key(course_id)
        exclude_users = get_aggregate_exclusion_user_ids(course_key)
        grade_complete_match_range = getattr(settings, 'GRADEBOOK_GRADE_COMPLETE_PROFORMA_MATCH_RANGE', 0.01)
        grades_qs = StudentGradebook.objects.filter(course_id__exact=course_key, user__is_active=True,
                                                    user__courseenrollment__is_active=True,
                                                    user__courseenrollment__course_id__exact=course_key).\
            exclude(user_id__in=exclude_users)
        grades_complete_qs = grades_qs.filter(proforma_grade__lte=F('grade') + grade_complete_match_range,
                                              proforma_grade__gt=0)
        enrolled_qs = CourseEnrollment.objects.filter(course_id__exact=course_key, user__is_active=True,
                                                      is_active=True).exclude(user_id__in=exclude_users)
        users_started_qs = StudentProgress.objects.filter(course_id__exact=course_key, user__is_active=True,
                                                          user__courseenrollment__is_active=True,
                                                          user__courseenrollment__course_id__exact=course_key)\
            .exclude(user_id__in=exclude_users)
        modules_completed_qs = CourseModuleCompletion.get_actual_completions()\
            .filter(course_id__exact=course_key,
                    user__courseenrollment__is_active=True,
                    user__courseenrollment__course_id__exact=course_key,
                    user__is_active=True)\
            .exclude(user_id__in=exclude_users)
        active_users_qs = StudentModule.objects\
            .filter(course_id__exact=course_key, student__is_active=True,
                    student__courseenrollment__is_active=True,
                    student__courseenrollment__course_id__exact=course_key)\
            .exclude(student_id__in=exclude_users)

        organization = request.query_params.get('organization', None)
        if organization:
            enrolled_qs = enrolled_qs.filter(user__organizations=organization)
            grades_complete_qs = grades_complete_qs.filter(user__organizations=organization)
            users_started_qs = users_started_qs.filter(user__organizations=organization)
            modules_completed_qs = modules_completed_qs.filter(user__organizations=organization)
            active_users_qs = active_users_qs.filter(student__organizations=organization)

        group_ids = get_ids_from_list_param(self.request, 'groups')
        if group_ids:
            enrolled_qs = enrolled_qs.filter(user__groups__in=group_ids).distinct()
            grades_complete_qs = grades_complete_qs.filter(user__groups__in=group_ids).distinct()
            users_started_qs = users_started_qs.filter(user__groups__in=group_ids).distinct()
            modules_completed_qs = modules_completed_qs.filter(user__groups__in=group_ids).distinct()
            active_users_qs = active_users_qs.filter(student__groups__in=group_ids).distinct()

        total_enrolled = enrolled_qs.filter(created__lt=start_dt).count()
        total_started_count = users_started_qs.filter(created__lt=start_dt).aggregate(Count('user', distinct=True))
        total_started = total_started_count['user__count'] or 0
        enrolled_series = get_time_series_data(
            enrolled_qs, start_dt, end_dt, interval=interval,
            date_field='created', date_field_model=CourseEnrollment,
            aggregate=Count('id', distinct=True)
        )
        started_series = get_time_series_data(
            users_started_qs, start_dt, end_dt, interval=interval,
            date_field='created', date_field_model=StudentProgress,
            aggregate=Count('user', distinct=True)
        )
        completed_series = get_time_series_data(
            grades_complete_qs, start_dt, end_dt, interval=interval,
            date_field='modified', date_field_model=StudentGradebook,
            aggregate=Count('id', distinct=True)
        )
        modules_completed_series = get_time_series_data(
            modules_completed_qs, start_dt, end_dt, interval=interval,
            date_field='created', date_field_model=CourseModuleCompletion,
            aggregate=Count('id', distinct=True)
        )

        # active users are those who accessed course in last 24 hours
        start_dt = start_dt - timedelta(hours=24)
        end_dt = end_dt - timedelta(hours=24)
        active_users_series = get_time_series_data(
            active_users_qs, start_dt, end_dt, interval=interval,
            date_field='modified', date_field_model=StudentModule,
            aggregate=Count('student', distinct=True)
        )

        not_started_series = []
        for enrolled, started in zip(enrolled_series, started_series):
            not_started_series.append((started[0], (total_enrolled + enrolled[1]) - (total_started + started[1])))
            total_started += started[1]
            total_enrolled += enrolled[1]

        data = {
            'users_not_started': not_started_series,
            'users_started': started_series,
            'users_completed': completed_series,
            'modules_completed': modules_completed_series,
            'users_enrolled': enrolled_series,
            'active_users': active_users_series
        }

        return Response(data, status=status.HTTP_200_OK)


class CoursesMetricsGradesLeadersList(SecureListAPIView):
    """
    ### The CoursesMetricsGradesLeadersList view allows clients to retrieve top 3 users who are leading
    in terms of grade and course average for the specified Course. If user_id parameter is given
    it would return user's position
    - URI: ```/api/courses/{course_id}/metrics/grades/leaders/?user_id={user_id}```
    - GET: Returns a JSON representation (array) of the users with grades
    To get more than 3 users use count parameter
    ``` /api/courses/{course_id}/metrics/grades/leaders/?count=3```
    To exclude users with certain roles from leaders
    ```/api/courses/{course_id}/metrics/grades/leaders/?exclude_roles=observer,assistant```
    ### Use Cases/Notes:
    * Example: Display grades leaderboard of a given course
    * Example: Display position of a users in a course in terms of grade and course avg
    """

    def get(self, request, course_id):  # pylint: disable=W0613,W0221
        """
        GET /api/courses/{course_id}/grades/leaders/
        """
        user_id = self.request.query_params.get('user_id', None)
        group_ids = get_ids_from_list_param(self.request, 'groups')
        count = self.request.query_params.get('count', 3)
        exclude_roles = css_param_to_list(self.request, 'exclude_roles')

        data = {}
        course_avg = 0  # pylint: disable=W0612
        if not course_exists(request, request.user, course_id):
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        course_key = get_course_key(course_id)
        # Users having certain roles (such as an Observer) are excluded from aggregations
        exclude_users = get_aggregate_exclusion_user_ids(course_key, roles=exclude_roles)
        leaderboard_data = StudentGradebook.generate_leaderboard(course_key,
                                                                 user_id=user_id,
                                                                 group_ids=group_ids,
                                                                 count=count,
                                                                 exclude_users=exclude_users)

        serializer = CourseLeadersSerializer(leaderboard_data['queryset'], many=True)
        data['leaders'] = serializer.data  # pylint: disable=E1101
        data['course_avg'] = leaderboard_data['course_avg']
        if 'user_position' in leaderboard_data:
            data['user_position'] = leaderboard_data['user_position']
        if 'user_grade' in leaderboard_data:
            data['user_grade'] = leaderboard_data['user_grade']

        return Response(data, status=status.HTTP_200_OK)

"""
Django database models supporting the gradebook app
"""
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import models
from django.db.models import Avg, Max, Min, Count, F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _
from model_utils.fields import AutoCreatedField, AutoLastModifiedField

from model_utils.models import TimeStampedModel
from student.models import CourseEnrollment
from xmodule_django.models import CourseKeyField

from gradebook.api_utils import is_int

class StudentGradebook(models.Model):
    """
    StudentGradebook is essentially a container used to cache calculated
    grades (see courseware.grades.grade), which can be an expensive operation.
    """
    user = models.ForeignKey(User, db_index=True)
    course_id = CourseKeyField(db_index=True, max_length=255, blank=True)
    grade = models.FloatField(db_index=True)
    proforma_grade = models.FloatField()
    progress_summary = models.TextField(blank=True)
    grade_summary = models.TextField()
    grading_policy = models.TextField()
    # We can't use TimeStampedModel here because those fields are not indexed.
    created = AutoCreatedField(_('created'), db_index=True)
    modified = AutoLastModifiedField(_('modified'), db_index=True)

    class Meta(object):
        """
        Meta information for this Django model
        """
        unique_together = (('user', 'course_id'),)

    @classmethod
    def generate_leaderboard(cls, course_key, user_id=None, group_ids=None, count=3, exclude_users=None):
        """
        Assembles a data set representing the Top N users, by grade, for a given course.
        Optionally provide a user_id to include user-specific info.  For example, you
        may want to view the Top 5 users, but also need the data for the logged-in user
        who may actually be currently located in position #10.

        data = {
            'course_avg': 0.873,
            'queryset': [
                {'id': 123, 'username': 'testuser1', 'grade': 0.92, 'created': '2014-01-15 06:27:54'},
                {'id': 983, 'username': 'testuser2', 'grade': 0.91, 'created': '2014-06-27 01:15:54'},
                {'id': 246, 'username': 'testuser3', 'grade': 0.90, 'created': '2014-03-19 04:54:54'},
                {'id': 357, 'username': 'testuser4', 'grade': 0.89, 'created': '2014-12-01 08:38:54'},
            ]
            ### IF USER ID SPECIFIED (in this case user_id=246) ###
            'user_position': 4,
            'user_grade': 0.89
        }

        If there is a discrepancy between the number of gradebook entries and the overall number of enrolled
        users (excluding any users who should be excluded), then we modify the course average to account for
        those users who currently lack gradebook entries.  We assume zero grades for these users because they
        have not yet submitted a response to a scored assessment which means no grade has been calculated.
        """
        exclude_users = exclude_users or []
        data = {}
        data['course_avg'] = 0
        data['course_max'] = 0
        data['course_min'] = 0
        data['course_count'] = 0
        data['queryset'] = []

        total_user_count = CourseEnrollment.objects.users_enrolled_in(course_key).exclude(id__in=exclude_users).count()

        if total_user_count:
            # Generate the base data set we're going to work with
            queryset = StudentGradebook.objects.select_related('user')\
                .filter(course_id__exact=course_key, user__is_active=True, user__courseenrollment__is_active=True,
                        user__courseenrollment__course_id__exact=course_key).exclude(user__id__in=exclude_users)

            aggregates = queryset.aggregate(Avg('grade'), Max('grade'), Min('grade'), Count('user'))
            gradebook_user_count = aggregates['user__count']

            if gradebook_user_count:
                # Calculate the class average
                course_avg = aggregates['grade__avg']
                if course_avg is not None:
                    # Take into account any ungraded students (assumes zeros for grades...)
                    course_avg = course_avg / total_user_count * gradebook_user_count

                    # Fill up the response container
                    data['course_avg'] = float("{0:.3f}".format(course_avg))
                    data['course_max'] = aggregates['grade__max']
                    data['course_min'] = aggregates['grade__min']
                    data['course_count'] = gradebook_user_count

                if group_ids:
                    queryset = queryset.filter(user__groups__in=group_ids).distinct()

                # Construct the leaderboard as a queryset
                data['queryset'] = queryset.values(
                    'user__id',
                    'user__username',
                    'grade',
                    'modified')\
                    .order_by('-grade', 'modified')[:count]
                # If a user_id value was provided, we need to provide some additional user-specific data to the caller
                if user_id:
                    result = cls.get_user_position(
                        course_key,
                        user_id,
                        exclude_users=exclude_users,
                        group_ids=group_ids,
                    )
                    data.update(result)

        return data

    @classmethod
    def get_user_position(cls, course_key, user_id, exclude_users=None, group_ids=None):
        """
        Helper method to return the user's position in the leaderboard for Proficiency
        """
        exclude_users = exclude_users or []
        data = {'user_position': 0, 'user_grade': 0}
        user_grade = 0
        users_above = 0
        user_time_scored = timezone.now()
        try:
            user_queryset = StudentGradebook.objects.get(course_id__exact=course_key, user__id=user_id)
        except StudentGradebook.DoesNotExist:
            user_queryset = None

        if user_queryset:
            user_grade = user_queryset.grade
            user_time_scored = user_queryset.created

        queryset = StudentGradebook.objects.select_related('user').filter(
            course_id__exact=course_key,
            user__is_active=True,
            user__courseenrollment__is_active=True,
            user__courseenrollment__course_id__exact=course_key
        ).exclude(
            user__in=exclude_users
        )

        if group_ids:
            queryset = queryset.filter(user__groups__in=group_ids).distinct()

        users_above = queryset.filter(
            Q(grade__gt=user_grade) |
            Q(grade=user_grade, modified__lt=user_time_scored)
        ).count()

        data['user_position'] = users_above + 1
        data['user_grade'] = user_grade

        return data

    @classmethod
    def get_num_users_completed(cls, course_key, exclude_users=None, org_ids=None, group_ids=None):
        """
        Returns count of users those who completed given course.
        """
        grade_complete_match_range = getattr(settings, 'GRADEBOOK_GRADE_COMPLETE_PROFORMA_MATCH_RANGE', 0.01)
        queryset = cls.objects.filter(
            course_id__exact=course_key,
            user__is_active=True,
            user__courseenrollment__is_active=True,
            user__courseenrollment__course_id__exact=course_key,
            proforma_grade__lte=F('grade') + grade_complete_match_range,
            proforma_grade__gt=0
        ).exclude(user__id__in=exclude_users)
        if org_ids:
            queryset = queryset.filter(user__organizations__in=org_ids)
        if group_ids:
            queryset = queryset.filter(user__groups__in=group_ids)

        return queryset.distinct().count()


class StudentGradebookHistory(TimeStampedModel):
    """
    A running audit trail for the StudentGradebook model.  Listens for
    post_save events and creates/stores copies of gradebook entries.
    """
    user = models.ForeignKey(User, db_index=True)
    course_id = CourseKeyField(db_index=True, max_length=255, blank=True)
    grade = models.FloatField()
    proforma_grade = models.FloatField()
    progress_summary = models.TextField(blank=True)
    grade_summary = models.TextField()
    grading_policy = models.TextField()

    @receiver(post_save, sender=StudentGradebook)
    def save_history(sender, instance, **kwargs):  # pylint: disable=no-self-argument, unused-argument
        """
        Event hook for creating gradebook entry copies
        """
        history_entries = StudentGradebookHistory.objects.filter(user=instance.user, course_id=instance.course_id)
        latest_history_entry = None
        if len(history_entries):
            latest_history_entry = history_entries[0]

        create_history_entry = False
        if latest_history_entry is not None:
            if (
                latest_history_entry.grade != instance.grade or
                latest_history_entry.proforma_grade != instance.proforma_grade or
                latest_history_entry.progress_summary != instance.progress_summary or
                latest_history_entry.grade_summary != instance.grade_summary or
                latest_history_entry.grading_policy != instance.grading_policy
            ):
                create_history_entry = True
        else:
            create_history_entry = True

        if create_history_entry:
            new_history_entry = StudentGradebookHistory(
                user=instance.user,
                course_id=instance.course_id,
                grade=instance.grade,
                proforma_grade=instance.proforma_grade,
                progress_summary=instance.progress_summary,
                grade_summary=instance.grade_summary,
                grading_policy=instance.grading_policy
            )
            new_history_entry.save()

### API MODELS ###

class GroupRelationship(TimeStampedModel):
    """
    The GroupRelationship model contains information describing the relationships of a group,
    which allows us to utilize Django's user/group/permission
    models and features instead of rolling our own.
    """
    group = models.OneToOneField(Group, primary_key=True)
    name = models.CharField(max_length=255)
    parent_group = models.ForeignKey('self',
                                     related_name="child_groups",
                                     blank=True, null=True, default=0)
    linked_groups = models.ManyToManyField('self',
                                           through="LinkedGroupRelationship",
                                           symmetrical=False,
                                           related_name="linked_to+"),
    record_active = models.BooleanField(default=True)

    def add_linked_group_relationship(self, to_group_relationship, symmetrical=True):
        """ Create a new group-group relationship """
        relationship = LinkedGroupRelationship.objects.get_or_create(
            from_group_relationship=self,
            to_group_relationship=to_group_relationship)
        if symmetrical:
            # avoid recursion by passing `symm=False`
            to_group_relationship.add_linked_group_relationship(self, False)
        return relationship

    def remove_linked_group_relationship(self, to_group_relationship, symmetrical=True):
        """ Remove an existing group-group relationship """
        LinkedGroupRelationship.objects.filter(
            from_group_relationship=self,
            to_group_relationship=to_group_relationship).delete()
        if symmetrical:
            # avoid recursion by passing `symm=False`
            to_group_relationship.remove_linked_group_relationship(self, False)
        return

    def get_linked_group_relationships(self):
        """ Retrieve an existing group-group relationship """
        efferent_relationships = LinkedGroupRelationship.objects.filter(from_group_relationship=self)
        matching_relationships = efferent_relationships
        return matching_relationships

    def check_linked_group_relationship(self, relationship_to_check, symmetrical=False):
        """ Confirm the existence of a possibly-existing group-group relationship """
        query = dict(
            to_group_relationships__from_group_relationship=self,
            to_group_relationships__to_group_relationship=relationship_to_check,
        )
        if symmetrical:
            query.update(
                from_group_relationships__to_group_relationship=self,
                from_group_relationships__from_group_relationship=relationship_to_check,
            )
        return GroupRelationship.objects.filter(**query).exists()


class LinkedGroupRelationship(TimeStampedModel):
    """
    The LinkedGroupRelationship model manages self-referential two-way
    relationships between group entities via the GroupRelationship model.
    Specifying the intermediary table allows for the definition of additional
    relationship information
    """
    from_group_relationship = models.ForeignKey(GroupRelationship,
                                                related_name="from_group_relationships",
                                                verbose_name="From Group")
    to_group_relationship = models.ForeignKey(GroupRelationship,
                                              related_name="to_group_relationships",
                                              verbose_name="To Group")
    record_active = models.BooleanField(default=True)


class CourseGroupRelationship(TimeStampedModel):
    """
    The CourseGroupRelationship model contains information describing the
    link between a course and a group.  A typical use case for this table
    is to manage the courses for an XSeries or other sort of program.
    """
    course_id = models.CharField(max_length=255, db_index=True)
    group = models.ForeignKey(Group, db_index=True)
    record_active = models.BooleanField(default=True)


class GroupProfile(TimeStampedModel):
    """
    This table will provide additional tables regarding groups. This has a foreign key to
    the auth_groups table
    """

    class Meta(object):
        """
        Meta class for modifying things like table name
        """
        db_table = "auth_groupprofile"

    group = models.OneToOneField(Group, db_index=True)
    group_type = models.CharField(null=True, max_length=32, db_index=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    data = models.TextField(blank=True)  # JSON dictionary for generic key/value pairs
    record_active = models.BooleanField(default=True)


class CourseContentGroupRelationship(TimeStampedModel):
    """
    The CourseContentGroupRelationship model contains information describing the
    link between a particular courseware element (chapter, unit, video, etc.)
    and a group.  A typical use case for this table is to support the concept
    of a student workgroup for a given course, where the project is actually
    a Chapter courseware element.
    """
    course_id = models.CharField(max_length=255, db_index=True)
    content_id = models.CharField(max_length=255, db_index=True)
    group_profile = models.ForeignKey(GroupProfile, db_index=True)
    record_active = models.BooleanField(default=True)

    class Meta(object):
        """
        Mapping model to enable grouping of course content such as chapters
        """
        unique_together = ("course_id", "content_id", "group_profile")


class APIUserQuerySet(models.query.QuerySet):
    """ Custom QuerySet to modify id based lookup """
    def filter(self, *args, **kwargs):
        if 'id' in kwargs and not is_int(kwargs['id']):
            kwargs['anonymoususerid__anonymous_user_id'] = kwargs['id']
            del kwargs['id']
        return super(APIUserQuerySet, self).filter(*args, **kwargs)


class APIUserManager(models.Manager):
    """ Custom Manager """
    def get_queryset(self):
        return APIUserQuerySet(self.model)


class APIUser(User):
    """
    A proxy model for django's auth.User to add AnonymousUserId fallback
    support in User lookups
    """
    objects = APIUserManager()

    class Meta(object):
        """ Meta attribute to make this a proxy model"""
        proxy = True

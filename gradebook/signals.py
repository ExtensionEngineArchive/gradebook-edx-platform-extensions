"""
Signal handlers supporting various gradebook use cases
"""
import logging

from django.dispatch import receiver

from courseware.signals import score_changed
from util.signals import course_deleted

from gradebook.models import StudentGradebook, StudentGradebookHistory
from gradebook.tasks import update_user_gradebook


log = logging.getLogger(__name__)


@receiver(score_changed, dispatch_uid="lms.courseware.score_changed")
def on_score_changed(sender, **kwargs):
    """
    Listens for a 'score_changed' signal invoke grade book update task
    """
    user_id = kwargs['user'].id
    course_key = unicode(kwargs['course_key'])
    update_user_gradebook.delay(course_key, user_id)


@receiver(course_deleted)
def on_course_deleted(sender, **kwargs):  # pylint: disable=W0613
    """
    Listens for a 'course_deleted' signal and when observed
    removes model entries for the specified course
    """
    course_key = kwargs['course_key']
    StudentGradebook.objects.filter(course_id=course_key).delete()
    StudentGradebookHistory.objects.filter(course_id=course_key).delete()

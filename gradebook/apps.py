"""
app configuration
"""
from django.apps import AppConfig


class SolutionsAppGradebookConfig(AppConfig):
    name = 'gradebook'
    verbose_name = 'gradebook app'

    def ready(self):
        pass

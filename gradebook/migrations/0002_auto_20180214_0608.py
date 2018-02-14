# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gradebook', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='studentgradebook',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='studentgradebook',
            name='user',
        ),
        migrations.RemoveField(
            model_name='studentgradebookhistory',
            name='user',
        ),
        migrations.DeleteModel(
            name='StudentGradebook',
        ),
        migrations.DeleteModel(
            name='StudentGradebookHistory',
        ),
    ]

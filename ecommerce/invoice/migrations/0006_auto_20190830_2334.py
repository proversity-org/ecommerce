# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-08-30 23:34
from __future__ import unicode_literals

from django.db import migrations
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('invoice', '0005_auto_20180119_0903'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='created',
            field=django_extensions.db.fields.CreationDateTimeField(auto_now_add=True, verbose_name='created'),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='modified',
            field=django_extensions.db.fields.ModificationDateTimeField(auto_now=True, verbose_name='modified'),
        ),
    ]

# Generated by Django 5.1.6 on 2025-03-03 10:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0015_cleaners_isavailable'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cleaners',
            name='bookings',
        ),
    ]

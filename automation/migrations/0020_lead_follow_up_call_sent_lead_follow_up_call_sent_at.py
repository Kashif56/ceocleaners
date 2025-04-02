# Generated by Django 5.1.6 on 2025-04-02 16:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0019_cleaners_rating'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='follow_up_call_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='lead',
            name='follow_up_call_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

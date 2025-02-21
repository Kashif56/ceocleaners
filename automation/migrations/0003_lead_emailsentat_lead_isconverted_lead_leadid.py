# Generated by Django 5.0.7 on 2025-01-26 11:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0002_lead'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='emailSentAt',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lead',
            name='isConverted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='lead',
            name='leadId',
            field=models.CharField(default='ld-32478', max_length=255),
            preserve_default=False,
        ),
    ]

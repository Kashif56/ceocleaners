# Generated by Django 5.1.6 on 2025-04-14 14:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0021_lead_address1_lead_address2_lead_city_lead_details_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='bathrooms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lead',
            name='bedrooms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lead',
            name='squareFeet',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lead',
            name='type_of_cleaning',
            field=models.CharField(blank=True, choices=[('standard', 'Standard Cleaning'), ('deep', 'Deep Cleaning'), ('moveinmoveout', 'Move In/Move Out'), ('airbnb', 'Airbnb Cleaning'), ('commercial', 'Commercial Cleaning')], max_length=255, null=True),
        ),
    ]

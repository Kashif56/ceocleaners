# Generated by Django 5.1.6 on 2025-04-04 11:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0007_remove_payment_invoice_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='paymentReminderSentAt',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

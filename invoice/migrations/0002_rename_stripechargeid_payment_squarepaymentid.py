# Generated by Django 5.1.6 on 2025-03-07 11:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('invoice', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payment',
            old_name='stripeChargeId',
            new_name='squarePaymentId',
        ),
    ]

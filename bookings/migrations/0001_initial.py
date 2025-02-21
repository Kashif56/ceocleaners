# Generated by Django 5.0.7 on 2025-02-15 15:59

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bookingId', models.CharField(blank=True, max_length=11, null=True, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254)),
                ('phoneNumber', models.CharField(max_length=20)),
                ('bedrooms', models.IntegerField()),
                ('bathrooms', models.IntegerField()),
                ('sqft', models.IntegerField()),
                ('address', models.CharField(max_length=255)),
                ('amount', models.IntegerField()),
                ('callSummary', models.TextField(blank=True, null=True)),
                ('scheduledDateTime', models.DateTimeField()),
                ('isCompleted', models.BooleanField(default=False)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoiceId', models.CharField(blank=True, max_length=11, null=True, unique=True)),
                ('amount', models.IntegerField(default=0)),
                ('isPaid', models.BooleanField(default=False)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('booking', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bookings.booking')),
            ],
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('paymentId', models.CharField(blank=True, max_length=11, null=True, unique=True)),
                ('amount', models.IntegerField(default=0)),
                ('paymentMethod', models.CharField(blank=True, max_length=50, null=True)),
                ('stripeChargeId', models.CharField(blank=True, max_length=11, null=True)),
                ('paidAt', models.DateTimeField(blank=True, null=True)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('invoice', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payment_details', to='bookings.invoice')),
            ],
        ),
    ]

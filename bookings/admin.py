from django.contrib import admin
from .models import Booking, BookingCustomAddons

# Register your models here.

admin.site.register(Booking)

admin.site.register(BookingCustomAddons)

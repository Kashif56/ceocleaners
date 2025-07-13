from django.db import models
from django.contrib.auth import get_user_model
import random
import string

from httpx._transports import default
from accounts.models import Business
from automation.models import Cleaners
from .payout_models import CleanerPayout

User = get_user_model()


serviceTypes = [
    ('standard', 'Standard Cleaning'),
    ('deep', 'Deep Cleaning'),
    ('moveinmoveout', 'Move In/Move Out'),
    ('airbnb', 'Airbnb Cleaning'),
    ('commercial', 'Commercial Cleaning'),
]

paymentMethods = [
    ('creditcard', 'Credit Card'),
    ('paypal', 'PayPal'),
    ('stripe', 'Stripe'),
    ('other', 'Other'),
]

recurringOptions = [
    ('one-time', 'One Time'),
    ('weekly', 'Weekly'),
    ('biweekly', 'Bi-weekly'),
    ('monthly', 'Monthly'),
]


class BookingCustomAddons(models.Model):
    addon = models.ForeignKey('accounts.CustomAddons', on_delete=models.CASCADE)
    qty = models.IntegerField(default=0)

    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.addon.addonName} - {self.qty}"


class Booking(models.Model):
    # Basic Information
    bookingId = models.CharField(max_length=11, unique=True, null=True, blank=True)
    business = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True)
    cleaner = models.ForeignKey(Cleaners, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Personal Information
    firstName = models.CharField(max_length=255, blank=True, null=True)
    lastName = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phoneNumber = models.CharField(max_length=20, blank=True, null=True)
    companyName = models.CharField(max_length=255, blank=True, null=True)
    
    # Address Information
    address1 = models.CharField(max_length=255, blank=True, null=True)
    address2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    stateOrProvince = models.CharField(max_length=100, blank=True, null=True)
    zipCode = models.CharField(max_length=10, blank=True, null=True)
    
    # Property Details
    bedrooms = models.IntegerField(default=0)
    bathrooms = models.IntegerField(default=0)
    squareFeet = models.IntegerField(default=0)
    
    # Service Information
    cleaningDate = models.DateField(null=True, blank=True)
    startTime = models.TimeField(null=True, blank=True)
    endTime = models.TimeField(null=True, blank=True)
    serviceType = models.CharField(max_length=50, choices=serviceTypes, null=True, blank=True)
    recurring = models.CharField(max_length=20, choices=recurringOptions, default='one-time')
    
    # Add-ons (Optional Services)
    addonDishes = models.IntegerField(null=True, blank=True)
    addonLaundryLoads = models.IntegerField(null=True, blank=True)
    addonWindowCleaning = models.IntegerField(null=True, blank=True)
    addonPetsCleaning = models.IntegerField(null=True, blank=True)
    addonFridgeCleaning = models.IntegerField(null=True, blank=True)
    addonOvenCleaning = models.IntegerField(null=True, blank=True)
    addonBaseboard = models.IntegerField(null=True, blank=True)
    addonBlinds = models.IntegerField(null=True, blank=True)
    addonGreenCleaning = models.IntegerField(null=True, blank=True)
    addonCabinetsCleaning = models.IntegerField(null=True, blank=True)
    addonPatioSweeping = models.IntegerField(null=True, blank=True)
    addonGarageSweeping = models.IntegerField(null=True, blank=True)
    
    customAddons = models.ManyToManyField(BookingCustomAddons, blank=True, related_name='bookings')
    
    # Additional Information
    otherRequests = models.TextField(blank=True, null=True)
    paymentMethod = models.CharField(max_length=20, choices=paymentMethods, null=True, blank=True)
    totalPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # cancelled
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Status Fields
    isCompleted = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    paymentReminderSentAt = models.DateTimeField(null=True, blank=True)
    dayBeforeReminderSentAt = models.DateTimeField(null=True, blank=True)
    hourBeforeReminderSentAt = models.DateTimeField(null=True, blank=True)

    arrival_confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.bookingId} for {self.firstName} {self.lastName}"
    
    def is_paid(self):
        """Check if booking has an invoice and is paid"""
        if hasattr(self, 'invoice') and self.invoice:
            # Check if invoice is marked as paid
            if self.invoice.isPaid:
                return True
            # Check payment details if they exist
            if hasattr(self.invoice, 'payment_details'):
                notPaidStatus = ['PENDING', 'FAILED']
                return self.invoice.payment_details.status not in notPaidStatus
            return False
        return False
    
    def get_payment_status(self):
        """Get the payment status of the booking."""
        if hasattr(self, 'invoice') and self.invoice:
            if hasattr(self.invoice, 'payment_details'):
                return self.invoice.payment_details.status
            return 'Unpaid'
        return 'No Invoice'
    
    def generateBookingId(self):
        prefix = "bk"
        id = random.choices(string.digits, k=5)
        return prefix + ''.join(id)
    
    def save(self, *args, **kwargs):
        if not self.bookingId:
            self.bookingId = self.generateBookingId()
        super().save(*args, **kwargs)
        
    def get_all_addons(self):
        """Return a list of all add-ons (standard and custom) for this booking."""
        addons = []
        
        # Standard add-ons
        addon_fields = {
            'addonDishes': 'Dishes',
            'addonLaundryLoads': 'Laundry',
            'addonWindowCleaning': 'Windows',
            'addonPetsCleaning': 'Pets',
            'addonFridgeCleaning': 'Fridge',
            'addonOvenCleaning': 'Oven',
            'addonBaseboard': 'Baseboard',
            'addonBlinds': 'Blinds',
            'addonGreenCleaning': 'Green Cleaning',
            'addonCabinetsCleaning': 'Cabinets',
            'addonPatioSweeping': 'Patio',
            'addonGarageSweeping': 'Garage'
        }
        
        for field, display_name in addon_fields.items():
            value = getattr(self, field, 0)
            if value:
                addons.append((display_name, value))
        
        # Custom add-ons
        for custom_addon in self.customAddons.all():
            addons.append((custom_addon.addon.addonName, custom_addon.qty))
        
        return addons
    

    def get_cleaner_payout(self):
        # TODO: Implement proper cleaner payment calculation
        # This is a placeholder until the proper payment system is implemented
        return 0.0

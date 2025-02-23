from django.db import models
from django.contrib.auth import get_user_model
import random


User = get_user_model()


class Business(models.Model):
    businessId = models.CharField(max_length=11, unique=True, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='business_set')
    businessName = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)

    bookingIntegrations = models.ManyToManyField('BookingIntegration', blank=True, related_name='integrated_businesses')

    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.businessName
    
    def save(self, *args, **kwargs):
        if not self.businessId:
            self.businessId = self.generateBusinessId()
        super().save(*args, **kwargs)

    def generateBusinessId(self):
        return f"BUS-{random.randint(1000000000, 9999999999)}"

class ApiCredential(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE)
    retellAPIKey = models.CharField(max_length=255, null=True, blank=True)
    retellWebhookURL = models.URLField(null=True, blank=True)
    voiceAgentNumber = models.CharField(max_length=20, null=True, blank=True)

    secretKey = models.CharField(max_length=255, null=True, blank=True, unique=True) # Business Secret Key to Verify Incoming Webhook Data

    def __str__(self):
        return self.business.businessName

class BookingIntegration(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='primary_integration')
    serviceName = models.CharField(max_length=50, null=True, blank=True)
    apiKey = models.CharField(max_length=255, null=True, blank=True)
    webhookUrl = models.URLField(null=True, blank=True)

    emailHostUser = models.CharField(max_length=255, null=True, blank=True)
    emailHostPasswrod = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.business.businessName


class BusinessSettings(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='settings')
    
    # Base Pricing
    bedroomPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bathroomPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    depositFee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxPercent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Square Feet Multipliers
    sqftMultiplierStandard = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sqftMultiplierDeep = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sqftMultiplierMoveinout = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sqftMultiplierAirbnb = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Add-on Prices
    addonPriceDishes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceLaundry = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceWindow = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPricePets = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceFridge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceOven = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceBaseboard = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceBlinds = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceGreen = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceCabinets = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPricePatio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    addonPriceGarage = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    customAddons = models.ManyToManyField('CustomAddons', blank=True, related_name='business_settings')
    
    # Commercial Booking
    commercialRequestLink = models.URLField(max_length=500, null=True, blank=True)
    
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Settings for {self.business.businessName}"
    
    class Meta:
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"


class CustomAddons(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='business_custom_addons')
    addonName = models.CharField(max_length=255, null=True, blank=True)
    addonPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return self.addonName
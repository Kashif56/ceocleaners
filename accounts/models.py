from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
import random
import pytz


User = get_user_model()

URL = settings.BASE_URL

PAYMENT_METHODS = [
    ('square', 'Square'),
    ('stripe', 'Stripe'),
    ('paypal', 'PayPal'),
]


JOB_ASSIGNMENT_OPTIONS = [
    ('high_rated', 'Auto-assign by points rating'),
    ('all_available', 'Send Job to available cleaners'),
]

class Business(models.Model):
    businessId = models.CharField(max_length=11, unique=True, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='business_set')
    businessName = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    square_card_id = models.CharField(max_length=255, null=True, blank=True, help_text="Square payment card ID for recurring payments")
    square_customer_id = models.CharField(max_length=255, null=True, blank=True, help_text="Square customer ID for recurring payments")
    auto_upgrade = models.BooleanField(default=False, help_text="Automatically upgrade to next plan when usage exceeds limits")
    timezone = models.CharField(max_length=50, default='UTC', help_text="Business timezone (e.g., 'America/New_York', 'Europe/London')")

    isActive = models.BooleanField(default=False)
    isApproved = models.BooleanField(default=False)
    isRejected = models.BooleanField(default=False)

    defaultPaymentMethod = models.CharField(max_length=255, null=True, blank=True, help_text="Default payment method for collecting payments", choices=PAYMENT_METHODS)

    job_assignment = models.CharField(max_length=255, null=True, blank=True, help_text="Job assignment method", choices=JOB_ASSIGNMENT_OPTIONS, default='all_available')

    useCall = models.BooleanField(default=False)
    timeToWait = models.IntegerField(default=0)

    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.businessName
    
    def save(self, *args, **kwargs):
        if not self.businessId:
            self.businessId = self.generateBusinessId()
        super().save(*args, **kwargs)

    def generateBusinessId(self):
        return f"BUS-{random.randint(1000, 9999)}"

    def get_square_credentials(self):
        return self.square_credentials
    
    def has_setup_fee(self):
        from subscription.models import SetupFee

        if SetupFee.objects.filter(business=self).exists():
            return True
        return False

    def has_availed_trial(self):
        from subscription.models import BusinessSubscription, SubscriptionPlan
        plan = SubscriptionPlan.objects.filter(plan_tier='trial', is_active=True, is_invite_only=False).first()
        subscription = BusinessSubscription.objects.filter(
            business=self,
            plan=plan
        )
        return subscription.exists()

        
    def active_subscription(self):
        from subscription.models import BusinessSubscription
        
        try:
            subscription = BusinessSubscription.objects.filter(
                business=self,
                is_active=True,
                status__in=['active', 'cancelled'],
                end_date__gte=timezone.now()
            ).first()

            if subscription and subscription.is_subscription_active():
                return subscription
            return None

        except Exception as e:
            # Log the error but don't crash
            print(f"Error getting active subscription: {e}")
            return None

    def get_timezone(self):
        """Get the business timezone as a pytz timezone object"""
        try:
            return pytz.timezone(self.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            return pytz.UTC

    def localize_datetime(self, dt):
        """Convert a datetime to the business's local timezone"""
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt)
        return dt.astimezone(self.get_timezone())

    def get_local_time(self):
        """Get current time in business's timezone"""
        return timezone.now().astimezone(self.get_timezone())

class ApiCredential(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE)
    # retellAPIKey = models.CharField(max_length=255, null=True, blank=True)
    # retellWebhookURL = models.URLField(null=True, blank=True)
    # voiceAgentNumber = models.CharField(max_length=20, null=True, blank=True)
    twilioSmsNumber = models.CharField(max_length=20, null=True, blank=True)
    twilioAccountSid = models.CharField(max_length=255, null=True, blank=True)
    twilioAuthToken = models.CharField(max_length=255, null=True, blank=True)
    twimlAppSid = models.CharField(max_length=255, null=True, blank=True)
    
    secretKey = models.CharField(max_length=255, null=True, blank=True, unique=True) # Business Secret Key to Verify Incoming Webhook Data

    def __str__(self):
        return self.business.businessName
    
    def getRetellUrl(self):
        return f"{URL}/webhook/{self.secretKey}/"
    
    def getThumbtackUrl(self):
        return f"{URL}/webhook/thumbtack/{self.secretKey}/"
    
    def getTwilioWebhookUrl(self):
        return f"{URL}/ai_agent/api/twilio/webhook/{self.secretKey}/"
    
    def getLeadWebhookUrl(self):
        return f"{URL}/lead/webhook/{self.secretKey}/"


class SMTPConfig(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE)
    host = models.CharField(max_length=255, null=True, blank=True)
    port = models.IntegerField(null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    from_name = models.CharField(max_length=255, null=True, blank=True)
    reply_to = models.CharField(max_length=255, null=True, blank=True)
    
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
    addonDataName = models.CharField(max_length=255, null=True, blank=True)
    addonPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def generate_data_name(self):
        if not self.addonName:
            return None
        # Convert to lowercase and replace spaces and special chars with underscore
        data_name = self.addonName.lower()
        data_name = ''.join(c if c.isalnum() else '_' for c in data_name)
        # Remove consecutive underscores and trim
        data_name = '_'.join(filter(None, data_name.split('_')))
        return data_name
    
    def save(self, *args, **kwargs):
        if not self.addonDataName and self.addonName:
            self.addonDataName = self.generate_data_name()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.addonName




class PasswordResetOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='password_reset_otp')
    otp = models.CharField(max_length=6)
    token = models.CharField(max_length=100, null=True, blank=True)
    is_used = models.BooleanField(default=False)
    failed_attempts = models.IntegerField(default=0)
    otp_sent_count = models.IntegerField(default=0)
    lock_expiry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Password Reset OTP for {self.user.username}"
    
    class Meta:
        verbose_name = "Password Reset OTP"
        verbose_name_plural = "Password Reset OTPs"



class SquareCredentials(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='square_credentials')
    access_token = models.CharField(max_length=255, null=True, blank=True)
    app_id = models.CharField(max_length=255, null=True, blank=True)
    location_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Square Credentials for {self.business.businessName}"


class StripeCredentials(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='stripe_credentials')
    stripe_secret_key = models.CharField(max_length=255, null=True, blank=True)
    stripe_publishable_key = models.CharField(max_length=255, null=True, blank=True)
    
    def __str__(self):
        return f"Stripe Credentials for {self.business.businessName}"
    

class PayPalCredentials(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='paypal_credentials')
    paypal_client_id = models.CharField(max_length=255, null=True, blank=True)
    paypal_secret_key = models.CharField(max_length=255, null=True, blank=True)
    
    def __str__(self):
        return f"PayPal Credentials for {self.business.businessName}"
    
    
    
    
    

class CleanerProfile(models.Model):
    """
    Links Django User to a Cleaner and Business
    Enables login for cleaners with restricted permissions
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cleaner_profile')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='cleaner_profiles')
    cleaner = models.OneToOneField('automation.Cleaners', on_delete=models.CASCADE, related_name='user_profile')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile for {self.cleaner.name} at {self.business.businessName}"



class ThumbtackProfile(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='thumbtack_profile')
    thumbtack_business_id = models.CharField(max_length=255, null=True, blank=True)
    access_token = models.CharField(max_length=2000, null=True, blank=True)
    refresh_token = models.CharField(max_length=2000, null=True, blank=True)

    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    

    def __str__(self):
        return self.business.businessName
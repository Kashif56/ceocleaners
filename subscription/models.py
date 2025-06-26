from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import Business
from django.conf import settings
import json
from datetime import datetime, timedelta
from django.utils.text import slugify

User = get_user_model()

class SubscriptionPlan(models.Model):
    """Model representing the different subscription plans available."""
    BILLING_CYCLE_CHOICES = [
        ('14_days', '14 Days'),
        ('monthly', 'Monthly'),
        ('2_months', '2 Months'),
        ('3_months', '3 Months'),
        ('6_months', '6 Months'),
        ('yearly', 'Yearly'),
        ('lifetime', 'Lifetime'),
    ]

    PLAN_TYPE_CHOICES = [
        ('free', 'Free'),
        ('paid', 'Paid'),
        ('trial', 'Trial'),
    ]
    
    PLAN_TIER_CHOICES = [
        ('starter', 'Starter'),
        ('professional', 'Professional'),
        ('enterprise', 'Enterprise'),
        ('trial', 'Trial'),
        ('custom', 'Custom'),
    ]

 
    name = models.CharField(max_length=100, help_text="Internal name for the plan", default="")
    display_name = models.CharField(max_length=100, help_text="Name displayed to users")
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES, default='monthly')
    plan_type = models.CharField(max_length=10, choices=PLAN_TYPE_CHOICES, default='paid')
    plan_tier = models.CharField(max_length=15, choices=PLAN_TIER_CHOICES, default='starter', help_text="The tier of the plan (Starter, Professional, Enterprise, etc.)")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Order in which plans should be displayed (lower numbers first)")
    is_active = models.BooleanField(default=True)
    is_invite_only = models.BooleanField(default=False, help_text="If enabled, this plan will only be available to users with a direct link")
    
    # Usage metrics
    voice_minutes = models.IntegerField(default=0)
    sms_messages = models.IntegerField(default=0)
    agents = models.IntegerField(default=1)
    leads = models.IntegerField(default=100)
    cleaners = models.IntegerField(default=5)
    
    # Replace JSON field with M2M relationship
    features = models.ManyToManyField('Feature', related_name='subscription_plans', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.display_name} ({self.get_billing_cycle_display()})"

    

    def get_invite_plan_url(self):
        return f"{settings.BASE_URL}/subscription/select-plan/{self.id}"
    
    def get_monthly_display_price(self):
        """Get the monthly display price for yearly plans with 20% discount applied."""
        if self.billing_cycle == 'yearly' or self.billing_cycle == 'Yearly':
            # Calculate monthly price (yearly price / 12)
            monthly_price = float(self.price) / 12
            # Apply 20% discount
            discounted_price = monthly_price * 0.8
            return round(discounted_price, 2)
        
        return float(self.price)
    
    def get_display_price(self):
        """Get the yearly display price for monthly plans with 20% discount applied."""
        if self.billing_cycle == 'yearly' or self.billing_cycle == 'Yearly':
           
            discounted_price = float(self.price) * float(0.8)
            return round(discounted_price, 2)
        
        return float(self.price)

    def get_display_label(self):
        if self.billing_cycle == 'yearly' or self.billing_cycle == 'Yearly':
            return f"/year"
        if self.billing_cycle == 'monthly' or self.billing_cycle == 'Monthly':
            return f"/month"
        if self.billing_cycle == '2_months' or self.billing_cycle == '2 Months':
            return f"/2 months"
        if self.billing_cycle == '3_months' or self.billing_cycle == '3 Months':
            return f"/3 months"
        if self.billing_cycle == '6_months' or self.billing_cycle == '6 Months':
            return f"/6 months"
        
        if self.plan_tier == 'trial' or self.plan_tier == 'Trial':
            return ""
        
        return ""
    
    def get_monthly_display_limits(self):
        """Get the monthly limits for yearly plans (yearly limits / 12)."""
        if self.billing_cycle == 'yearly' or self.billing_cycle == 'Yearly':
            return {
                'voice_minutes': round(self.voice_minutes / 12),
                'sms_messages': round(self.sms_messages / 12),
                'agents': self.agents,  # Agents don't change
                'leads': round(self.leads / 12),
                'cleaners': self.cleaners  # Cleaners don't change
            }
        return {
            'voice_minutes': self.voice_minutes,
            'sms_messages': self.sms_messages,
            'agents': self.agents,
            'leads': self.leads,
            'cleaners': self.cleaners
        }
    

    def get_next_billing_date(self):
        if self.billing_cycle == 'monthly' or self.billing_cycle == 'Monthly':
            return timezone.now() + timedelta(days=30)
        elif self.billing_cycle == 'yearly' or self.billing_cycle == 'Yearly':
            return timezone.now() + timedelta(days=365)
        elif self.billing_cycle == '2_months' or self.billing_cycle == '2 Months':
            return timezone.now() + timedelta(days=60)
        elif self.billing_cycle == '3_months' or self.billing_cycle == '3 Months':
            return timezone.now() + timedelta(days=90)
        elif self.billing_cycle == '6_months' or self.billing_cycle == '6 Months':
            return timezone.now() + timedelta(days=180)
        elif self.billing_cycle == '14_days' or self.billing_cycle == '14 Days':
            return timezone.now() + timedelta(days=14)
        
        return timezone.now() + timedelta(days=30)


class Feature(models.Model):
    """Model to store features that can be associated with subscription plans"""
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.display_name


class Coupon(models.Model):
    """Model representing discount coupons for subscription plans."""
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount Discount'),
    ]
    
    LIMIT_TYPE_CHOICES = [
        ('overall', 'Overall Usage Limit'),
        ('per_user', 'Per User Usage Limit'),
    ]
    
    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    applicable_plans = models.ManyToManyField(SubscriptionPlan, blank=True, related_name='coupons')
    
    # Usage limits
    limit_type = models.CharField(max_length=10, choices=LIMIT_TYPE_CHOICES, default='overall')
    usage_limit = models.PositiveIntegerField(null=True, blank=True)  # None means unlimited
    times_used = models.PositiveIntegerField(default=0)
    
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        if self.discount_type == 'percentage':
            return f"{self.code} - {self.discount_value}% off"
        return f"{self.code} - ${self.discount_value} off"
    
    def is_valid(self):
        """Check if the coupon is valid for use."""
        if not self.is_active:
            return False
        
        # Check expiry date
        if self.expiry_date and self.expiry_date < timezone.now().date():
            return False
        
        # Check overall usage limit
        if self.limit_type == 'overall' and self.usage_limit is not None and self.times_used >= self.usage_limit:
            return False
        
        return True
    
    def is_valid_for_user(self, user):
        """Check if the coupon is valid for a specific user."""
        # First check general validity
        if not self.is_valid():
            return False
            
        # For per-user limit, check user's usage count
        if self.limit_type == 'per_user' and self.usage_limit is not None:
            user_usage_count = CouponUsage.objects.filter(coupon=self, user=user).count()
            if user_usage_count >= self.usage_limit:
                return False
                
        return True
    
    def calculate_discount(self, original_price):
        """Calculate the discount amount based on the coupon type and value."""
        if not self.is_valid():
            return 0
        
        # Convert to Decimal to ensure consistent type handling
        from decimal import Decimal, ROUND_HALF_UP
        original_price = Decimal(str(original_price))
        
        if self.discount_type == 'percentage':
            discount = (original_price * Decimal(str(self.discount_value))) / Decimal('100')
            # Round to 1 decimal place
            return discount.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        else:  # fixed amount
            discount = min(Decimal(str(self.discount_value)), original_price)  # Don't discount more than the price
            # Round to 1 decimal place
            return discount.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    
    def apply_discount(self, original_price):
        """Apply the discount to the original price and return the discounted price."""
        from decimal import Decimal, ROUND_HALF_UP
        original_price = Decimal(str(original_price))
        discount = self.calculate_discount(original_price)
        final_price = max(original_price - discount, Decimal('0'))  # Ensure price doesn't go below 0
        # Round to 1 decimal place
        return final_price.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    
    def use_coupon(self):
        """Increment the usage count of the coupon."""
        self.times_used += 1
        self.save()
        return self.times_used

class CouponUsage(models.Model):
    """Model to track coupon usage per user."""
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coupon_usages')
    subscription = models.ForeignKey('BusinessSubscription', on_delete=models.SET_NULL, null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('coupon', 'user', 'subscription')
        
    def __str__(self):
        return f"{self.user.username} used {self.coupon.code} on {self.used_at.strftime('%Y-%m-%d')}"

class BusinessSubscription(models.Model):
    """Model representing a business's subscription to a plan."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('past_due', 'Past Due'),
        ('trialing', 'Trialing'),
        ('ended', 'Ended')
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='business_subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)
    next_plan_id = models.IntegerField(null=True, blank=True, help_text="ID of the plan to change to at next billing date")
    coupon_used = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    
    # Payment provider fields
    square_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    square_customer_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Legacy fields - keeping for backward compatibility
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business.businessName} - {self.plan.name} ({self.status})"
    
    def is_subscription_active(self):
        """Check if the subscription is currently active."""
        if not self.is_active:
            return False
        if self.status == 'past_due':
            return False
        if self.end_date and self.end_date < timezone.now():
            return False
        return True

    
    def days_remaining(self):
        """Calculate days remaining in the current billing cycle."""
        if not self.end_date:
            return None
        if self.end_date < timezone.now():
            return 0
        delta = self.end_date - timezone.now()
        return delta.days
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Track coupon usage if a coupon is applied
        if self.coupon_used and is_new:
            # Increment the overall usage counter
            self.coupon_used.times_used += 1
            self.coupon_used.save()
            
            # Record per-user usage - use get_or_create to prevent duplicates
            if self.business.user:
                CouponUsage.objects.get_or_create(
                    coupon=self.coupon_used,
                    user=self.business.user,
                    subscription=self
                )

class UsageTracker(models.Model):
    """Model for tracking usage metrics for a business."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='usage_metrics')
    date = models.DateField(default=timezone.now)
    metrics = models.JSONField(default=dict)  # Stores voice_minutes, voice_calls, sms_messages
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('business', 'date')
    
    def __str__(self):
        return f"Usage for {self.business.businessName} on {self.date}"
    
    @classmethod
    def increment_metric(cls, business, metric_name, increment_by=1):
        """Increment a specific usage metric for the business on the current date."""
        today = timezone.now().date()
        usage, created = cls.objects.get_or_create(
            business=business,
            date=today,
            defaults={'metrics': {}}
        )
        
        metrics = usage.metrics
        current_value = metrics.get(metric_name, 0)
        metrics[metric_name] = current_value + increment_by
        usage.metrics = metrics
        usage.save()
        
        return usage
    
    @classmethod
    def increment_minutes(cls, business, increment_by=1):
        """Increment voice minutes usage for the business."""
        return cls.increment_metric(business, 'voice_minutes', increment_by)
    
    @classmethod
    def increment_sms(cls, business, increment_by=1):
        """Increment SMS messages count for the business."""
        return cls.increment_metric(business, 'sms_messages', increment_by)
    
    @classmethod
    def increment_agents(cls, business, increment_by=1):
        """Increment active agents count for the business."""
        return cls.increment_metric(business, 'active_agents', increment_by)
    
    @classmethod
    def increment_leads(cls, business, increment_by=1):
        """Increment leads generated count for the business."""
        return cls.increment_metric(business, 'leads_generated', increment_by)
    
    @classmethod
    def get_usage_summary(cls, business, start_date=None, end_date=None):
        """
        Get a summary of usage metrics for a business within a date range.
        
        Args:
            business: The Business instance
            start_date: Start date for the summary (defaults to start of current month)
            end_date: End date for the summary (defaults to today)
            
        Returns:
            Dictionary with total usage metrics and daily breakdown
        """

        # Get active subscription
        active_subscription = business.active_subscription()    
        if start_date is None:
            # Default to start of current month
            start_date = active_subscription.start_date if active_subscription else timezone.now().date().replace(day=1)
        
        if end_date is None:
            end_date = active_subscription.end_date if active_subscription else timezone.now().date()
        
        # Get all usage records in the date range
        usage_records = cls.objects.filter(
            business=business,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        # Initialize summary with zero counts

        # Get Active Agents
        from retell_agent.models import RetellAgent
        from automation.models import Cleaners
        active_agents = RetellAgent.objects.filter(business=business).count()
        cleaners = Cleaners.objects.filter(business=business).count()
        
        summary = {
            'total': {
                'voice_minutes': 0,
                'sms_messages': 0,
                'active_agents': active_agents,
                'leads_generated': 0,
                'cleaners': cleaners
            },
            'daily': []
        }
        
        # Calculate totals and prepare daily breakdown
        for record in usage_records:
            # Add to totals
            for metric, value in record.metrics.items():
                if metric in summary['total']:
                    if metric == 'active_agents':
                        summary['total'][metric] = active_agents
                    elif metric == 'cleaners':
                        summary['total'][metric] = cleaners
                    else:
                        summary['total'][metric] += value
                else:
                    summary['total'][metric] = value
            
            # Add daily record
            daily_entry = {
                'date': record.date,
                'metrics': record.metrics
            }
            summary['daily'].append(daily_entry)
        
        # Get subscription limits for comparison
        if active_subscription:
            plan = active_subscription.plan
            summary['limits'] = {
                'voice_minutes': plan.voice_minutes,
                'sms_messages': plan.sms_messages,
                'active_agents': plan.agents,
                'leads_generated': plan.leads,
                'cleaners': plan.cleaners
            }
            
            # Calculate usage percentages
            summary['usage_percentage'] = {}
            for metric, limit in summary['limits'].items():
                if limit > 0:  # Avoid division by zero
                    usage = summary['total'].get(metric, 0)
                    summary['usage_percentage'][metric] = min(100, round((usage / limit) * 100))
                else:
                    summary['usage_percentage'][metric] = 0
        
        return summary

class BillingHistory(models.Model):
    """Model for tracking billing history and invoices."""
    STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='billing_records')
    subscription = models.ForeignKey(BusinessSubscription, on_delete=models.SET_NULL, null=True, related_name='billing_records')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    invoice_url = models.URLField(blank=True, null=True)
    billing_date = models.DateTimeField(default=timezone.now)
    details = models.JSONField(default=dict)  # For storing additional invoice details
    
    # Payment provider fields
    square_invoice_id = models.CharField(max_length=100, blank=True, null=True)
    square_payment_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Legacy field - keeping for backward compatibility
    stripe_invoice_id = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Invoice #{self.id} - {self.business.businessName} (${self.amount})"



class SetupFee(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='setup_fee')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    pait_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Setup Fee for {self.business.businessName} - ${self.amount}"
    
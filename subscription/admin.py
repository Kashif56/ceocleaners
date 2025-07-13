from django.contrib import admin
from .models import SubscriptionPlan, BusinessSubscription, UsageTracker, BillingHistory, Feature, Coupon, CouponUsage, SetupFee

class FeatureAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'display_name', 'description')
    ordering = ('display_name',)

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'billing_cycle', 'is_active')
    list_filter = ('billing_cycle', 'is_active')
    filter_horizontal = ('features',)  # This adds a nice widget for managing many-to-many relationships
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'price', 'billing_cycle', 'is_active', 'is_invite_only')
        }),
        ('Usage Metrics', {
            'fields': ('voice_minutes', 'sms_messages', 'agents', 'leads')
        }),
        ('Features', {
            'fields': ('features',)
        }),
    )

class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'is_active', 'expiry_date', 'times_used')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)

class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'user', 'used_at')
    list_filter = ('used_at',)
    search_fields = ('coupon__code', 'user__email')

class BusinessSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('business', 'plan', 'status', 'start_date', 'end_date', 'is_active')
    list_filter = ('status', 'is_active', 'plan')
    search_fields = ('business__name', 'stripe_subscription_id')
    date_hierarchy = 'start_date'

class UsageTrackerAdmin(admin.ModelAdmin):
    list_display = ('business', 'date', 'get_voice_minutes', 'get_voice_calls', 'get_sms_messages')
    list_filter = ('date',)
    search_fields = ('business__name',)
    date_hierarchy = 'date'
    
    def get_voice_minutes(self, obj):
        return obj.metrics.get('voice_minutes', 0)
    get_voice_minutes.short_description = 'Voice Minutes'
    
    def get_voice_calls(self, obj):
        return obj.metrics.get('voice_calls', 0)
    get_voice_calls.short_description = 'Voice Calls'
    
    def get_sms_messages(self, obj):
        return obj.metrics.get('sms_messages', 0)
    get_sms_messages.short_description = 'SMS Messages'

class BillingHistoryAdmin(admin.ModelAdmin):
    list_display = ('business', 'amount', 'status', 'billing_date')
    list_filter = ('status', 'billing_date')
    search_fields = ('business__name', 'stripe_invoice_id')
    date_hierarchy = 'billing_date'

admin.site.register(Feature, FeatureAdmin)
admin.site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin.site.register(Coupon, CouponAdmin)
admin.site.register(CouponUsage, CouponUsageAdmin)
admin.site.register(BusinessSubscription, BusinessSubscriptionAdmin)
admin.site.register(UsageTracker, UsageTrackerAdmin)
admin.site.register(BillingHistory, BillingHistoryAdmin)
admin.site.register(SetupFee)

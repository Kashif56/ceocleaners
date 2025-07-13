from django.contrib import admin
from django.contrib import messages
from .models import Business, BusinessSettings, ApiCredential, CustomAddons, PasswordResetOTP, SMTPConfig, SquareCredentials, StripeCredentials, PayPalCredentials, ThumbtackProfile


class BusinessAdmin(admin.ModelAdmin):
    list_display = ('businessName', 'user', 'phone', 'isActive', 'isApproved', 'createdAt')
    list_filter = ('isActive', 'isApproved', 'createdAt')
    search_fields = ('businessName', 'user__username', 'phone', 'address')
    readonly_fields = ('createdAt', 'updatedAt')
    actions = ['approve_businesses', 'reject_businesses']
    
    def approve_businesses(self, request, queryset):
        updated = queryset.update(isApproved=True, isActive=True)
        self.message_user(
            request,
            f'{updated} business(es) have been approved and activated.',
            messages.SUCCESS
        )
    approve_businesses.short_description = "Approve selected businesses"
    
    def reject_businesses(self, request, queryset):
        updated = queryset.update(isApproved=False, isActive=False)
        self.message_user(
            request,
            f'{updated} business(es) have been rejected and deactivated.',
            messages.WARNING
        )
    reject_businesses.short_description = "Reject selected businesses"


admin.site.register(Business, BusinessAdmin)
admin.site.register(BusinessSettings)
admin.site.register(ApiCredential)
admin.site.register(CustomAddons)
admin.site.register(SMTPConfig)
admin.site.register(PasswordResetOTP)
admin.site.register(SquareCredentials)
admin.site.register(StripeCredentials)
admin.site.register(PayPalCredentials)
admin.site.register(ThumbtackProfile)
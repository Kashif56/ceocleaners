from django.db import models
from accounts.models import Business
import json

class PlatformIntegration(models.Model):
    AUTH_TYPE_CHOICES = (
        ('none', 'No Authentication'),
        ('token', 'Token Authentication'),
        ('basic', 'Basic Authentication'),
    )

    PLATFORM_TYPE_CHOICES = (
        ('direct_api', 'Direct API Integration'),
        ('workflow', 'Workflow Automation Platform'),
    )

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='integrations')
    platform_type = models.CharField(max_length=20, choices=PLATFORM_TYPE_CHOICES, default='direct_api')
    name = models.CharField(max_length=255)
    base_url = models.URLField(help_text="Base URL for the API endpoint", blank=True, null=True)
    webhook_url = models.URLField(help_text="Webhook URL for workflow platforms", blank=True, null=True)

    headers = models.JSONField(default=dict, blank=True, help_text="HTTP headers to include with API requests")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.business.businessName}"

class DataMapping(models.Model):
    FIELD_TYPES = (
        ('string', 'Text'),
        ('number', 'Number'),
        ('boolean', 'True/False'),
        ('date', 'Date'),
        ('time', 'Time'),
        ('datetime', 'Date & Time'),
        ('array', 'Array/List'),
        ('object', 'Object')
    )

    platform = models.ForeignKey(PlatformIntegration, on_delete=models.CASCADE, related_name='mappings')
    source_field = models.CharField(max_length=255, help_text="Field name from your system")
    target_field = models.CharField(max_length=255, help_text="Field name expected by the platform")
    parent_path = models.CharField(max_length=255, blank=True, null=True, help_text="Dot-separated path for nested fields (e.g., customer.address)")
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES, default='string')
    is_required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=255, null=True, blank=True)
    order = models.IntegerField(default=0, help_text="Order within the parent object")

    class Meta:
        ordering = ['parent_path', 'order']

    def __str__(self):
        if self.parent_path:
            return f"{self.parent_path}.{self.target_field} <- {self.source_field}"
        return f"{self.target_field} <- {self.source_field}"

class IntegrationLog(models.Model):
    STATUS_CHOICES = (
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending')
    )

    platform = models.ForeignKey(PlatformIntegration, on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    request_data = models.JSONField()
    response_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.platform.name} - {self.status} - {self.created_at}"

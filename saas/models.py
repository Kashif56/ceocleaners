from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
# Here SaaS Platform Related Mdoels like Platform Settings will be Created to Give More Control to Admin to Enable or Disable 

class PlatformSettings(models.Model):
    setup_fee = models.BooleanField(default=True)
    setup_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    company_name = models.CharField(max_length=100, default="CleaningBiz AI")
    company_email = models.EmailField(default="support@cleaningbiz.ai")
    company_phone = models.CharField(max_length=20, default="+1-800-123-4567")
    company_address = models.TextField(blank=True, null=True)
    support_email = models.EmailField(default="support@cleaningbiz.ai")
    default_timezone = models.CharField(max_length=50, default="UTC")
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"

    def __str__(self):
        return f"Platform Settings"


class SupportTicket(models.Model):
    STATUS_CHOICES = (
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    
    CATEGORY_CHOICES = (
        ('bug', 'Bug Report'),
        ('feature', 'Feature Request'),
        ('support', 'Support Request'),
        ('billing', 'Billing Issue'),
        ('other', 'Other'),
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='bug')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_tickets')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    business = models.ForeignKey('accounts.Business', on_delete=models.CASCADE, null=True, blank=True)
    browser_info = models.TextField(blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    screenshot = models.ImageField(upload_to='ticket_screenshots/', blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Support Ticket'
        verbose_name_plural = 'Support Tickets'
    
    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"
    
    def resolve(self, user):
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.assigned_to = user
        self.save()


class TicketComment(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to='ticket_attachments/', blank=True, null=True)
    is_internal = models.BooleanField(default=False, help_text='Internal notes visible only to staff')
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.author} on {self.ticket.title}"


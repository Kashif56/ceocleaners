from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from django.conf import settings
import threading
import inspect

# Import the ActivityLog model
from admin_dashbaord.models import ActivityLog

# Thread local storage to store the current user
_thread_locals = threading.local()

def get_current_user():
    """Get the current user from thread local storage"""
    return getattr(_thread_locals, 'user', None)

def set_current_user(user):
    """Set the current user in thread local storage"""
    _thread_locals.user = user

class ActivityTrackingMiddleware:
    """
    Middleware to set the current user in thread local storage
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set the current user in thread local storage
        if request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)
        
        response = self.get_response(request)
        
        # Clear the thread local storage
        set_current_user(None)
        
        return response

# List of models to track
TRACKED_MODELS = [
    # Subscription models
    'subscription.models.SubscriptionPlan',
    'subscription.models.BusinessSubscription',
    'subscription.models.Feature',
    'subscription.models.Coupon',
    'subscription.models.CouponUsage',
    'subscription.models.UsageTracker',
    'subscription.models.BillingHistory',
    'subscription.models.SetupFee',
    
    # Invoice models
    'invoice.models.Invoice',
    'invoice.models.Payment',
    
    # Accounts models
    'accounts.models.Business',
    'accounts.models.ApiCredential',
    'accounts.models.SMTPConfig',
    'accounts.models.BusinessSettings',
    'accounts.models.CustomAddons',
    'accounts.models.PasswordResetOTP',
    'accounts.models.SquareCredentials',
    'accounts.models.StripeCredentials',
    'accounts.models.PayPalCredentials',
    'accounts.models.CleanerProfile',
    'accounts.models.ThumbtackProfile',
    
    # Booking models
    'bookings.models.Booking',
    'bookings.models.BookingCustomAddons',
    
    # Automation models
    'automation.models.Lead',
    'automation.models.Cleaners',
    'automation.models.CleanerAvailability',
    'automation.models.OpenJob',
    
    # AI Agent models
    'ai_agent.models.Messages',
    'ai_agent.models.Chat',
    'ai_agent.models.AgentConfiguration',
    
    # Analytics models
    'analytics.models.PageView',
    'analytics.models.Event',
    
    # Retell Agent models
    'retell_agent.models.RetellAgent',
    'retell_agent.models.RetellLLM',
    'retell_agent.models.RetellCall',
]

def get_model_display_name(instance):
    """Get a human-readable name for the model instance"""
    if hasattr(instance, '__str__'):
        return str(instance)
    elif hasattr(instance, 'name'):
        return instance.name
    elif hasattr(instance, 'title'):
        return instance.title
    elif hasattr(instance, 'id'):
        return f"{instance.__class__.__name__} #{instance.id}"
    else:
        return instance.__class__.__name__

def log_activity(instance, activity_type, user=None):
    """
    Log an activity for a model instance
    
    Args:
        instance: The model instance
        activity_type: The type of activity ('create', 'update', 'delete')
        user: The user who performed the action (optional)
    """
    # Get the user from thread local storage if not provided
    if user is None:
        user = get_current_user()
    
    # Skip if no user is available
    if user is None:
        return
    
    # Get content type
    content_type = ContentType.objects.get_for_model(instance)
    
    # Create a description based on the activity type
    model_name = instance.__class__.__name__
    display_name = get_model_display_name(instance)
    
    if activity_type == 'create':
        description = f"Created {model_name}: {display_name}"
    elif activity_type == 'update':
        description = f"Updated {model_name}: {display_name}"
    elif activity_type == 'delete':
        description = f"Deleted {model_name}: {display_name}"
    else:
        description = f"{activity_type.capitalize()} {model_name}: {display_name}"
    
    # Create metadata with object details
    metadata = {
        'model': model_name,
        'app_label': content_type.app_label,
        'object_id': instance.id if hasattr(instance, 'id') else None,
    }
    
    # Add changed fields for update operations
    if activity_type == 'update' and hasattr(instance, '_changed_fields'):
        metadata['changed_fields'] = instance._changed_fields
    
    # Create the activity log
    ActivityLog.objects.create(
        user=user,
        activity_type=activity_type,
        description=description,
        content_type=content_type,
        object_id=instance.id if hasattr(instance, 'id') else None,
        metadata=metadata
    )

def track_model_changes():
    """
    Set up signal handlers for all tracked models
    """
    # Dictionary to store original values for update tracking
    _original_values = {}
    

    
    @receiver(pre_save)
    def track_update_pre_save(sender, instance, **kwargs):
        """Track field changes before saving"""
        # Get the full model path
        model_path = sender.__module__ + '.' + sender.__name__
        
        # Skip if the model is not in the tracked models list
        if model_path not in TRACKED_MODELS:
            return
        
        # Skip if this is a new instance (will be handled by post_save)
        if not instance.pk:
            return
        
        # Store the original values for comparison
        try:
            original = sender.objects.get(pk=instance.pk)
            _original_values[instance] = {
                field.name: getattr(original, field.name)
                for field in sender._meta.fields
                if field.name != 'id'
            }
            print(f"Activity Tracker: Pre-save tracking for {model_path} - {instance}")
        except sender.DoesNotExist:
            # Object doesn't exist yet, skip
            pass
    
    @receiver(post_save)
    def track_create_update(sender, instance, created, **kwargs):
        """Track create and update operations"""
        # Get the full model path
        model_path = sender.__module__ + '.' + sender.__name__
        
        # Skip if the model is not in the tracked models list
        if model_path not in TRACKED_MODELS:
            return
        
        # Get the current user
        user = get_current_user()
        if not user:
            print(f"Activity Tracker: No user found for {model_path} - {instance}")
            return
        
        if created:
            # It's a create operation
            print(f"Activity Tracker: Logging CREATE for {model_path} - {instance} by {user.username}")
            log_activity(instance, 'create', user)
        else:
            # It's an update operation
            # Find changed fields
            if instance in _original_values:
                changed_fields = []
                for field_name, original_value in _original_values[instance].items():
                    current_value = getattr(instance, field_name)
                    if original_value != current_value:
                        changed_fields.append({
                            'field': field_name,
                            'old_value': str(original_value),
                            'new_value': str(current_value)
                        })
                
                # Store changed fields on the instance for the log_activity function
                instance._changed_fields = changed_fields
                
                # Only log if fields actually changed
                if changed_fields:
                    print(f"Activity Tracker: Logging UPDATE for {model_path} - {instance} by {user.username} with {len(changed_fields)} changes")
                    log_activity(instance, 'update', user)
                else:
                    print(f"Activity Tracker: No changes detected for {model_path} - {instance}")
                
                # Clean up
                if instance in _original_values:
                    del _original_values[instance]
    
    @receiver(post_delete)
    def track_delete(sender, instance, **kwargs):
        """Track delete operations"""
        # Get the full model path
        model_path = sender.__module__ + '.' + sender.__name__
        
        # Skip if the model is not in the tracked models list
        if model_path not in TRACKED_MODELS:
            return
        
        # Get the current user
        user = get_current_user()
        if not user:
            print(f"Activity Tracker: No user found for DELETE of {model_path} - {instance}")
            return
        
        # Log the delete operation
        print(f"Activity Tracker: Logging DELETE for {model_path} - {instance} by {user.username}")
        log_activity(instance, 'delete', user)

# Initialize tracking
track_model_changes()

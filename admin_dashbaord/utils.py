from .models import ActivityLog
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import json

def log_activity(user, activity_type, description, request=None, obj=None, metadata=None):
    """
    Utility function to log user activities
    
    Parameters:
    - user: The user performing the action
    - activity_type: Type of activity (from ActivityLog.ACTIVITY_TYPES)
    - description: Description of the activity
    - request: The request object (optional, for IP address)
    - obj: The object being acted upon (optional)
    - metadata: Additional data to store (optional)
    """
    ip_address = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
    
    # Prepare metadata with additional context
    if metadata is None:
        metadata = {}
    
    # Add request information if available
    if request:
        request_data = {
            'method': request.method,
            'path': request.path,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'referer': request.META.get('HTTP_REFERER', ''),
        }
        
        # Add query parameters if present
        if request.GET:
            request_data['query_params'] = dict(request.GET.items())
        
        # Add non-sensitive POST data if present (exclude password fields)
        if request.POST:
            safe_post = {}
            for key, value in request.POST.items():
                if 'password' not in key.lower() and 'token' not in key.lower():
                    safe_post[key] = value
            if safe_post:
                request_data['post_data'] = safe_post
        
        metadata['request'] = request_data
    
    # Add timestamp information
    metadata['timestamp_iso'] = timezone.now().isoformat()
    
    # Add object information if available
    if obj:
        try:
            # Try to get a meaningful representation of the object
            obj_repr = str(obj)
            obj_data = {
                'id': obj.id,
                'model': obj.__class__.__name__,
                'app': obj._meta.app_label,
                'repr': obj_repr
            }
            
            # Add specific fields for certain model types
            if hasattr(obj, 'name'):
                obj_data['name'] = obj.name
            if hasattr(obj, 'email'):
                obj_data['email'] = obj.email
            if hasattr(obj, 'username'):
                obj_data['username'] = obj.username
                
            metadata['object'] = obj_data
        except Exception as e:
            # If there's an error getting object data, just note the error
            metadata['object_error'] = str(e)
    
    activity_log = ActivityLog(
        user=user,
        activity_type=activity_type,
        description=description,
        ip_address=ip_address,
        metadata=metadata
    )
    
    # Add content object if provided
    if obj:
        content_type = ContentType.objects.get_for_model(obj)
        activity_log.content_type = content_type
        activity_log.object_id = obj.id
    
    activity_log.save()
    return activity_log


def log_model_change(user, instance, change_type, request=None, changes=None):
    """
    Utility function to log model changes (create, update, delete)
    
    Parameters:
    - user: The user performing the action
    - instance: The model instance being modified
    - change_type: 'create', 'update', or 'delete'
    - request: The request object (optional)
    - changes: Dictionary of field changes for updates {field_name: (old_value, new_value)}
    """
    model_name = instance.__class__.__name__
    
    # Create appropriate description based on change type
    if change_type == 'create':
        description = f"Created {model_name}: {str(instance)}"
    elif change_type == 'update':
        description = f"Updated {model_name}: {str(instance)}"
    elif change_type == 'delete':
        description = f"Deleted {model_name}: {str(instance)}"
    else:
        description = f"{change_type.capitalize()} {model_name}: {str(instance)}"
    
    # Create metadata with changes if provided
    metadata = {}
    if changes:
        metadata['changes'] = changes
    
    return log_activity(
        user=user,
        activity_type=change_type,
        description=description,
        request=request,
        obj=instance,
        metadata=metadata
    )


def get_object_activity_history(obj, limit=None):
    """
    Get activity history for a specific object
    
    Parameters:
    - obj: The object to get history for
    - limit: Optional limit on number of records to return
    """
    content_type = ContentType.objects.get_for_model(obj)
    activities = ActivityLog.objects.filter(
        content_type=content_type,
        object_id=obj.id
    ).select_related('user').order_by('-timestamp')
    
    if limit:
        activities = activities[:limit]
    
    return activities


def get_user_activity_history(user, limit=None):
    """
    Get activity history for a specific user
    
    Parameters:
    - user: The user to get history for
    - limit: Optional limit on number of records to return
    """
    activities = ActivityLog.objects.filter(user=user).order_by('-timestamp')
    
    if limit:
        activities = activities[:limit]
    
    return activities

from django.utils import timezone
import pytz

def timezone_context(request):
    """
    Context processor to add timezone information to all templates.
    Makes the following variables available in templates:
    - user_timezone: The timezone object for the current user
    - current_time: Current time in the user's timezone
    """
    user_timezone = getattr(request, 'timezone', pytz.UTC)
    current_time = timezone.now().astimezone(user_timezone)
    
    return {
        'user_timezone': user_timezone,
        'current_time': current_time,
    }

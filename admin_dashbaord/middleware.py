import re
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import User, AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.urls import resolve
from .models import ActivityLog

class UserActivityMiddleware(MiddlewareMixin):
    """
    Middleware to track user page visits and activities
    """
    # URLs to ignore for tracking (e.g., static files, admin media)
    IGNORED_URLS = [
        r'^/static/',
        r'^/media/',
        r'^/admin/jsi18n/',
        r'^/__debug__/',
        r'^/favicon.ico',
    ]
    
    def process_request(self, request):
        """Process the request and log user activity"""
        # Skip if URL is in ignored list
        path = request.path_info.lstrip('/')
        for pattern in self.IGNORED_URLS:
            if re.match(pattern, request.path):
                return None
        
        # Skip if user is not authenticated
        if not request.user.is_authenticated:
            return None
        
        # Get the URL name if available
        try:
            url_name = resolve(request.path_info).url_name
            namespace = resolve(request.path_info).namespace
            view_name = f"{namespace}:{url_name}" if namespace else url_name
        except:
            view_name = "unknown"
        
        # Get the IP address
        ip_address = self.get_client_ip(request)
        
        # Create metadata
        metadata = {
            'method': request.method,
            'path': request.path,
            'view_name': view_name,
            'query_params': dict(request.GET.items()),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'referer': request.META.get('HTTP_REFERER', ''),
        }
        
        # Create a description
        description = f"Visited {view_name} page"
        print(description)
        
        # Log the activity
        ActivityLog.objects.create(
            user=request.user,
            activity_type='other',  # Page visit is considered 'other'
            description=description,
            ip_address=ip_address,
            metadata=metadata
        )
        
        return None
    
    def get_client_ip(self, request):
        """Get the client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

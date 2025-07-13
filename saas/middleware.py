from django.shortcuts import redirect
from django.urls import resolve, reverse
from .models import PlatformSettings


class MaintenanceModeMiddleware:
    """
    Middleware to check if the site is in maintenance mode and redirect
    to a maintenance view for non-staff users.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if we're in maintenance mode
        try:
            settings = PlatformSettings.objects.get(pk=1)
            maintenance_mode = settings.maintenance_mode
        except PlatformSettings.DoesNotExist:
            PlatformSettings.objects.create(maintenance_mode=False)
            maintenance_mode = False
        
       

        # Skip maintenance mode for staff users and admin URLs
        is_staff = request.user.is_authenticated and request.user.is_staff
        admin_url = request.path.startswith('/admin/') or request.path.startswith('/admin-dashboard/')
        
        # Allow login page to be accessible during maintenance
        login_url = request.path.startswith('/accounts/login')
        
        # Don't redirect if already on maintenance page
        maintenance_url = request.path.startswith(reverse('saas:maintenance'))
        
        if maintenance_mode and not is_staff and not admin_url and not login_url and not maintenance_url:
            return redirect('saas:maintenance')
        
        response = self.get_response(request)
        return response

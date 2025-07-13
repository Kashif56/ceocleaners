from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.contrib import messages
from django.utils import timezone
import pytz


class BusinessApprovalMiddleware:
    """
    Middleware to check if a business is approved before allowing access to certain views.
    If the business is not approved, the user is redirected to the approval_pending page.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Skip middleware if user is not authenticated or is admin
        # if not request.user.is_authenticated or request.user.is_staff or request.user.is_superuser:
        #     return self.get_response(request)
            
        # Skip for cleaner users - they'll be handled by CleanerAccessMiddleware
        if request.user.groups.filter(name='Cleaner').exists():
            return self.get_response(request)
            
        # List of URLs that should be accessible without approval
        exempt_urls = [
            'login', 'logout', 'signup', 'register_business', 
            'approval_pending', 'profile', 'update_profile', 'change_password',
            'forgot_password', 'verify_otp', 'resend_otp', 'reset_password',
            'admin:index', 'admin:login', 'select_plan', 'subscription_management', 'manage_card',
            'process_payment'
        ]
        
        # Also skip if URL is exempt or is admin URL
        try:
            current_url = resolve(request.path_info).url_name
            if current_url in exempt_urls or request.path.startswith('/admin'):
                return self.get_response(request)
        except:
            # If URL can't be resolved, just continue
            pass
            
        # Check if user has a business
        if hasattr(request.user, 'business_set') and request.user.business_set.exists():
            business = request.user.business_set.first()
            
            # If business is not approved, redirect to approval_pending
            try:
                current_url = resolve(request.path_info).url_name
                if not business.isApproved and current_url != 'approval_pending':
                    messages.warning(request, "You haven’t subscribed to a plan yet. Start with our Trial Plan to unlock full access to all features and get started right away!")
                    return redirect('accounts:approval_pending')
                else:
                    pass
            except:
                pass
        
        # Business owner with approved business - allow access to all pages
        return self.get_response(request)


class CleanerAccessMiddleware:
    """
    Middleware to restrict cleaners to only access their own pages and data.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Skip middleware if user is not authenticated or is admin
        if not request.user.is_authenticated or request.user.is_staff or request.user.is_superuser:
            return self.get_response(request)
        
        # Only process for cleaner users with 'Cleaner' group
        if not request.user.groups.filter(name='Cleaner').exists():
            return self.get_response(request)
        
        # IMPORTANT: Explicitly block register-business URL for cleaners
        # This is a critical check that needs to happen early
        if '/accounts/register-business/' in request.path:
            messages.error(request, 'Cleaners cannot register a business. Access denied.')
            print("BLOCKED: Cleaner attempted to access register-business page")
            
            # If user has a cleaner profile, redirect to their detail page
            if hasattr(request.user, 'cleaner_profile') and hasattr(request.user.cleaner_profile, 'cleaner'):
                cleaner_id = str(request.user.cleaner_profile.cleaner.id)
                return redirect(f'/cleaners/{cleaner_id}/')
            # Otherwise redirect to home
            return redirect('/')
        
        # Handle users with Cleaner group but no cleaner_profile yet
        if not hasattr(request.user, 'cleaner_profile'):
            # Don't redirect to register business page, this would be wrong for cleaners
            # Instead let them access public pages
            return self.get_response(request)
        
        # At this point, we know the user is a cleaner with a profile
        cleaner_id = str(request.user.cleaner_profile.cleaner.id)
        
        # List of URLs that are always accessible
        exempt_urls = [
            'login', 'logout', 
            'change_password', 'LandingPage', 
            'PricingPage', 'FeaturesPage', 'AboutUsPage',
            'ContactUsPage', 'DocsPage', 'PrivacyPolicyPage', 
            'TermsOfServicePage', 'sitemap',
            'update_cleaner_profile',
            'update_cleaner_schedule', 'add_specific_date', 'delete_specific_date',
            'accept_open_job', 'reject_open_job'
        ]
        
        # Public paths always accessible
        allowed_paths = [
            '/accounts/logout/',
            '/pricing/',
            '/features/',
            '/about-us/',
            '/contact-us/',
            '/docs/'
        ]
        
        try:
            current_url = resolve(request.path_info).url_name
            
            # If on exempt URL, allow access
            if current_url in exempt_urls:
                return self.get_response(request)
            
            # Check for cleaner detail pages - cleaner can only see their own page
            if current_url in ['cleaner_detail', 'cleaner_monthly_schedule']:
                url_cleaner_id = resolve(request.path_info).kwargs.get('cleaner_id')
                if str(url_cleaner_id) == cleaner_id:
                    return self.get_response(request)
                else:
                    return redirect(f'/cleaners/{cleaner_id}/')
        except Exception as e:
            # Continue with path-based checks if URL resolution fails
            pass
        
        # Check if in allowed paths
        for path in allowed_paths:
            if request.path.startswith(path):
                return self.get_response(request)
        
        # Allow access to cleaner's own URLs
        if '/cleaners/' in request.path and cleaner_id in request.path:
            return self.get_response(request)
        
        # Allow access to jobs
        if '/jobs/' in request.path:
            return self.get_response(request)
        
        # Allow access to payouts
        if '/booking/payouts/' in request.path:
            return self.get_response(request)
        
        # Allow access to confirmation URLs
        if '/confirm-arrival/' in request.path or '/confirm-completed/' in request.path:
            return self.get_response(request)
        
        # Special check for login-related pages
        if '/accounts/' in request.path and any(x in request.path for x in ['/login/', '/logout/']):
            return self.get_response(request)
        # Not allowed - redirect to appropriate cleaner detail page
        # Always redirect to cleaner detail page for any unauthorized access
        try:
            # Use the cleaner detail page URL as the default redirect
            cleaner_url = f'/cleaners/{cleaner_id}/'
            return redirect(cleaner_url)
        except Exception as e:
            # Log the error
            pass
            
            # Use absolute hardcoded redirect as last resort
            cleaner_url = f'/cleaners/{cleaner_id}/'
            return redirect(cleaner_url)


class TimezoneMiddleware:
    """
    Middleware to set the timezone for each request based on the business's timezone setting.
    For business users, it uses their business timezone.
    For cleaner users, it uses their associated business's timezone.
    For unauthenticated users, it defaults to UTC.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Default timezone is UTC
        user_timezone = pytz.UTC
        
        if request.user.is_authenticated:
            # For business users
            if hasattr(request.user, 'business_set') and request.user.business_set.exists():
                business = request.user.business_set.first()
                user_timezone = business.get_timezone()
            
            # For cleaner users
            elif hasattr(request.user, 'cleaner_profile') and hasattr(request.user.cleaner_profile, 'business'):
                business = request.user.cleaner_profile.business
                user_timezone = business.get_timezone()
        
        # Set the timezone for this thread/request
        timezone.activate(user_timezone)
        
        # Store timezone in request for template context
        request.timezone = user_timezone
        
        response = self.get_response(request)
        
        # Reset to default timezone after the response is generated
        timezone.deactivate()
        
        return response

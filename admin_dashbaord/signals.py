from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .utils import log_activity

# This file now only handles login/logout signals
# Database operation tracking is handled by activity_tracker.py

@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    """Track user login events"""
    log_activity(
        user=user,
        activity_type='login',
        description=f"User {user.username} logged in",
        request=request,
        metadata={
            'login_time': user.last_login.isoformat() if user.last_login else None
        }
    )

@receiver(user_logged_out)
def track_user_logout(sender, request, user, **kwargs):
    """Track user logout events"""
    if user:  # User might be None if session was expired
        log_activity(
            user=user,
            activity_type='logout',
            description=f"User {user.username} logged out",
            request=request
        )

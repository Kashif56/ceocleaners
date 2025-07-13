from django.utils import timezone
import pytz
from datetime import datetime

def get_timezone_choices():
    """
    Returns a list of timezone choices for use in forms.
    Format: [(timezone_name, timezone_display_name), ...]
    """
    return [(tz, tz.replace('_', ' ')) for tz in pytz.common_timezones]

def convert_to_utc(dt, source_timezone):
    """
    Convert a datetime from a specific timezone to UTC.
    If dt is naive (no timezone info), it's assumed to be in source_timezone.
    Returns a timezone-aware datetime in UTC.
    """
    if dt is None:
        return None
        
    # If datetime is already timezone aware, convert it to UTC
    if dt.tzinfo is not None:
        return dt.astimezone(pytz.UTC)
        
    # If datetime is naive, assume it's in source_timezone
    if isinstance(source_timezone, str):
        source_timezone = pytz.timezone(source_timezone)
        
    # Localize the naive datetime to source_timezone, then convert to UTC
    return source_timezone.localize(dt).astimezone(pytz.UTC)

def convert_from_utc(dt, target_timezone):
    """
    Convert a datetime from UTC to a specific timezone.
    If dt is naive (no timezone info), it's assumed to be in UTC.
    Returns a timezone-aware datetime in the target timezone.
    """
    if dt is None:
        return None
        
    # If datetime is naive, assume it's in UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        # Ensure it's in UTC
        dt = dt.astimezone(pytz.UTC)
        
    # Convert to target timezone
    if isinstance(target_timezone, str):
        target_timezone = pytz.timezone(target_timezone)
        
    return dt.astimezone(target_timezone)

def format_datetime(dt, target_timezone=None, format_str=None):
    """
    Format a datetime for display in a specific timezone.
    If target_timezone is None, the datetime is displayed as is.
    If format_str is None, a default format is used.
    """
    if dt is None:
        return ""
        
    if target_timezone:
        dt = convert_from_utc(dt, target_timezone)
        
    if format_str:
        return dt.strftime(format_str)
    else:
        # Default format: "January 1, 2023, 3:45 PM"
        return dt.strftime("%B %d, %Y, %I:%M %p")

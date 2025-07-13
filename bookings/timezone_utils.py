from django.utils import timezone
import pytz
from datetime import datetime, date, time

def localize_booking_datetime(booking, field_name=None):
    """
    Converts booking datetime fields to the business's timezone.
    If field_name is provided, only that field is converted.
    Otherwise, all datetime fields are converted.
    
    Returns a dictionary of converted values.
    """
    if not booking or not booking.business:
        return {}
    
    business_timezone = booking.business.get_timezone()
    result = {}
    
    # Define fields to convert
    datetime_fields = ['createdAt', 'updatedAt', 'paymentReminderSentAt', 
                      'dayBeforeReminderSentAt', 'hourBeforeReminderSentAt',
                      'arrival_confirmed_at', 'completed_at', 'cancelled_at']
    
    # If a specific field is requested
    if field_name:
        if field_name in datetime_fields:
            field_value = getattr(booking, field_name)
            if field_value:
                result[field_name] = field_value.astimezone(business_timezone)
        return result
    
    # Convert all datetime fields
    for field in datetime_fields:
        field_value = getattr(booking, field, None)
        if field_value:
            result[field] = field_value.astimezone(business_timezone)
    
    # Handle special case for cleaning date and time
    # These are stored as separate date and time fields
    if booking.cleaningDate and booking.startTime:
        # Create a datetime object from date and time
        naive_dt = datetime.combine(booking.cleaningDate, booking.startTime)
        # Make it timezone aware in UTC
        utc_dt = timezone.make_aware(naive_dt, pytz.UTC)
        # Convert to business timezone
        local_dt = utc_dt.astimezone(business_timezone)
        
        result['cleaning_datetime'] = local_dt
        result['cleaning_date_local'] = local_dt.date()
        result['start_time_local'] = local_dt.time()
    
    if booking.cleaningDate and booking.endTime:
        # Create a datetime object from date and time
        naive_dt = datetime.combine(booking.cleaningDate, booking.endTime)
        # Make it timezone aware in UTC
        utc_dt = timezone.make_aware(naive_dt, pytz.UTC)
        # Convert to business timezone
        local_dt = utc_dt.astimezone(business_timezone)
        
        result['end_time_local'] = local_dt.time()
    
    return result

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

def get_utc_datetime(date_value, time_value, source_timezone):
    """
    Combine a date and time into a UTC datetime.
    The date and time are assumed to be in the source_timezone.
    Returns a timezone-aware datetime in UTC.
    """
    if not date_value or not time_value:
        return None
    
    # Create a naive datetime from date and time
    naive_dt = datetime.combine(date_value, time_value)
    
    # Convert to UTC
    return convert_to_utc(naive_dt, source_timezone)

def convert_local_to_utc(date_str, time_str, source_timezone):
    """
    Convert date and time strings from local timezone to UTC datetime.
    
    Args:
        date_str (str): Date string in format 'YYYY-MM-DD'
        time_str (str): Time string in format 'HH:MM'
        source_timezone (str): Timezone name (e.g., 'America/New_York')
        
    Returns:
        datetime: UTC datetime object
    """
    if not date_str or not time_str:
        return None
        
    try:
        # Parse date and time strings
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        
        # Combine into a datetime object
        local_datetime = datetime.combine(date_obj, time_obj)
        
        # Convert to UTC
        return convert_to_utc(local_datetime, source_timezone)
    except (ValueError, TypeError) as e:
        print(f"Error converting date/time to UTC: {e}")
        # Return current UTC time as fallback
        return timezone.now()

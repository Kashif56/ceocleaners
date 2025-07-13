import os
import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import make_aware, is_naive
from retell import Retell
from accounts.models import Business, ApiCredential, BusinessSettings, CustomAddons, SMTPConfig
from bookings.models import Booking, BookingCustomAddons
from invoice.models import Invoice
from .models import Cleaners, CleanerAvailability
from django.conf import settings

from .utils import calculateAddonsAmount, calculateAmount, sendInvoicetoClient, sendEmailtoClientInvoice
import dateparser
import pytz
import traceback

# Function to get available cleaners for a business
def get_cleaners_for_business(business, exclude_ids=None, assignment_check_null=False):
    
    all_cleaners = Cleaners.objects.filter(business=business)
    
    active_cleaners = all_cleaners.filter(isActive=True)
    
    # Apply available filter
    available_cleaners = active_cleaners
    
    cleaners = available_cleaners
    
    # Apply rating filter if needed
    if business.job_assignment == 'high_rated' and not assignment_check_null:
        max_rating = max(cleaners.values_list('rating', flat=True))
        high_rated_cleaners = cleaners.filter(rating__gte=max_rating)
 
        cleaners = high_rated_cleaners
    
    # Apply exclusion filter if needed
    if exclude_ids:
        filtered_cleaners = cleaners.exclude(id__in=exclude_ids)
        
        cleaners = filtered_cleaners
    

    return cleaners

# Function to get cleaner availabilities for a specific day
def get_cleaner_availabilities(cleaner, date_to_check):
    # Ensure date_to_check is a datetime object
    from datetime import datetime
    if isinstance(date_to_check, str):
        try:
            # Try to parse the string as a datetime
            date_to_check = datetime.strptime(date_to_check, "%Y-%m-%d %H:%M")
        except ValueError:
            # If it fails, it might be just a date string
            try:
                date_to_check = datetime.strptime(date_to_check, "%Y-%m-%d")
            except ValueError:
                # If all parsing fails, return None
                return None
    
    specific_availability = CleanerAvailability.objects.filter(
        cleaner=cleaner,
        availability_type='specific',
        specific_date=date_to_check.date()
    ).first()
    
    if specific_availability:
        # If it's an off day, return None
        if specific_availability.offDay:
            return None
        return specific_availability
    
    # Fall back to weekly schedule
    week_day = date_to_check.strftime('%A')
    weekly_availability = CleanerAvailability.objects.filter(
        cleaner=cleaner,
        availability_type='weekly',
        dayOfWeek=week_day
    ).first()
    
    # If it's an off day in the weekly schedule, return None
    if weekly_availability and weekly_availability.offDay:
        return None
    
    return weekly_availability

# Function to check if a timeslot is available
def is_slot_available(cleaners, time_to_check, available_cleaners=None):
    if available_cleaners is None:
        available_cleaners = []
    
    available_cleaners.clear()
    
    logs = []
    logs.append(f"Checking availability for {time_to_check.strftime('%Y-%m-%d %H:%M')}")
    logs.append(f"Found {len(cleaners)} cleaners to check")
    
    for cleaner in cleaners:
        logs.append(f"\nChecking cleaner: {cleaner.name}")
        
        # Get availability for this date/time
        cleaner_availability = get_cleaner_availabilities(cleaner, time_to_check)
        
        if cleaner_availability is None:
            logs.append(f"❌ {cleaner.name} doesn't work on {time_to_check.strftime('%A')} {time_to_check.strftime('%Y-%m-%d')}")
            continue

        # Check if time is within cleaner's working hours
        if not (cleaner_availability.startTime <= time_to_check.time() <= cleaner_availability.endTime):
            logs.append(f"❌ Time {time_to_check.strftime('%H:%M')} is outside {cleaner.name}'s working hours ({cleaner_availability.startTime.strftime('%H:%M')} - {cleaner_availability.endTime.strftime('%H:%M')})")
            continue

        # Check for conflicting bookings
        conflicting_booking = Booking.objects.filter(
            cleaner=cleaner,
            cleaningDate=time_to_check.date(),
            startTime__lte=time_to_check.time(),
            endTime__gt=time_to_check.time()
        ).exists()

        if conflicting_booking:
            logs.append(f"❌ {cleaner.name} has a conflicting booking at this time")
            continue

        # If we get here, the cleaner is available
        logs.append(f"✅ {cleaner.name} is available!")
        available_cleaners.append(cleaner)

    if len(available_cleaners) > 0:
        logs.append(f"\n✨ Found {len(available_cleaners)} available cleaner(s)!")
    else:
        logs.append("\n❌ No cleaners available for this time slot")

    # Return True if we found any available cleaners, along with the logs
    return len(available_cleaners) > 0, logs


# FUnction to Find All Available Cleaners for a given time slot
def find_all_available_cleaners(cleaners, time_to_check):
    print(f"Finding available cleaners at time: {time_to_check}")
    print(f"Number of cleaners to check: {cleaners.count() if hasattr(cleaners, 'count') else len(cleaners)}")
    
    available_cleaners = []
    for cleaner in cleaners:
        print(f"Checking availability for cleaner ID: {cleaner.id}")
        availability = get_cleaner_availabilities(cleaner, time_to_check)
        print(f"Cleaner {cleaner.id} availability result: {availability}")
        
        if availability is None:
            print(f"Cleaner {cleaner.id} is not available at {time_to_check}")
            continue
        
        print(f"Cleaner {cleaner.id} is available at {time_to_check}")
        available_cleaners.append(cleaner.id)
    
    print(f"Total available cleaners found: {len(available_cleaners)}")
    return available_cleaners





# Function to find an available cleaner
def find_available_cleaner(cleaners, time_to_check):
    """Find the best available cleaner for the given time slot based on rating."""
    print("\nFinding available cleaner for time:", time_to_check)
    print("Number of cleaners to check:", len(cleaners))
    
    available_cleaners = []
    
    for cleaner in cleaners:
        print("\nChecking cleaner:", cleaner.name)
        
        # Check cleaner's availability for the requested date/time
        availability = get_cleaner_availabilities(cleaner, time_to_check)

        if not availability:
            print(f"No availability found for {cleaner.name} on {time_to_check.strftime('%A')} {time_to_check.strftime('%Y-%m-%d')}")
            continue  # Skip if the cleaner is not available that day

        print(f"Found availability for {cleaner.name}: {availability.startTime} - {availability.endTime}")

        if not (availability.startTime <= time_to_check.time() <= availability.endTime):
            print(f"Time {time_to_check.time()} is outside {cleaner.name}'s working hours")
            continue

        # Check for conflicting bookings
        conflicting_booking = Booking.objects.filter(
            cleaner=cleaner,
            cleaningDate=time_to_check.date(),
            startTime__lte=time_to_check.time(),
            endTime__gte=time_to_check.time()
        ).exists()

        if conflicting_booking:
            print(f"{cleaner.name} has a conflicting booking")
            continue

        print(f"✓ {cleaner.name} is available (Rating: {cleaner.rating}/5)")
        available_cleaners.append(cleaner)

    if not available_cleaners:
        print("No available cleaners found for this time slot")
        return None
    
    # Sort available cleaners by rating (highest first)
    best_cleaner = max(available_cleaners, key=lambda c: c.rating)
    print(f"Selected best cleaner: {best_cleaner.name} with rating {best_cleaner.rating}/5")
    return best_cleaner

# Function to find alternate available slots
def find_alternate_slots(cleaners, datetimeToCheck, max_alternates=3):
    """
    Find up to `max_alternates` alternate available timeslots.
    If no slots exist on the requested day, search the next available day.
    
    Note: datetimeToCheck should already be in the business's timezone.
    """
    logs = []
    logs.append(f"\nLooking for alternate slots after {datetimeToCheck.strftime('%Y-%m-%d %H:%M')}")
    
    alternate_slots = []
    time_increment = timedelta(hours=1)
    max_attempts = 24  # Increased to search more slots
    
    # Start from the next hour
    next_time = datetimeToCheck.replace(minute=0, second=0, microsecond=0) + time_increment
    
    # Define business hours (9 AM to 5 PM by default)
    business_start_hour = 9
    business_end_hour = 17
    
    # Track days we've already checked to avoid checking the same day multiple times
    checked_days = set()
    
    while len(alternate_slots) < max_alternates and max_attempts > 0:
        available_cleaners = []
        
        # Skip times outside of business hours (9 AM - 5 PM)
        current_hour = next_time.hour
        current_date = next_time.date()
        date_str = current_date.strftime('%Y-%m-%d')
        
        # If we've already checked this day and found no slots, skip to next day
        if date_str in checked_days and current_hour >= business_end_hour:
            # Move to 9 AM the next day
            next_time = (next_time + timedelta(days=1)).replace(hour=business_start_hour, minute=0, second=0, microsecond=0)
            continue
        
        # If outside business hours, adjust time
        if current_hour < business_start_hour:
            # Move to start of business hours
            next_time = next_time.replace(hour=business_start_hour, minute=0, second=0, microsecond=0)
        elif current_hour >= business_end_hour:
            # Move to start of business hours the next day
            next_time = (next_time + timedelta(days=1)).replace(hour=business_start_hour, minute=0, second=0, microsecond=0)
            
        # Check if this slot is available
        is_available, slot_logs = is_slot_available(cleaners, next_time, available_cleaners)
        logs.extend(slot_logs)
        
        # Add the date to checked days
        checked_days.add(date_str)
        
        if is_available and len(available_cleaners) > 0:
            # Format the datetime in ISO format for consistency
            alternate_slots.append(next_time.strftime("%Y-%m-%d %I:%M %p"))
            logs.append(f"✅ Found alternate slot at {next_time.strftime('%Y-%m-%d %I:%M %p')} with {len(available_cleaners)} cleaner(s)")
        
        # Move to the next time slot
        next_time += time_increment
        max_attempts -= 1

    if len(alternate_slots) == 0:
        logs.append("❌ No alternate slots found within the search period")
    else:
        logs.append(f"✨ Found {len(alternate_slots)} alternate slot(s)")

    return alternate_slots, logs

# API endpoint to check availability
from rest_framework.decorators import api_view
@api_view(['POST'])
def check_availability_retell(request, secretKey):
    """
    API endpoint for Retell AI to check appointment availability.
    """
    try:
        if request.method != "POST":
            return JsonResponse({"error": "Invalid request method"}, status=405)
        
        apiCreds = ApiCredential.objects.get(secretKey=secretKey)
        business = apiCreds.business

        # Parse request body
        post_data = json.loads(request.body)

        # Extract parameters
        args = post_data.get("args", {})
        cleaningDateTime = args.get("cleaningDateTime")

        if not cleaningDateTime:
            return JsonResponse({"error": "Missing required field: cleaningDateTime"}, status=400)

        time_to_check = datetime.fromisoformat(cleaningDateTime)
        cleaners = get_cleaners_for_business(business, assignment_check_null=True)
        available_cleaners = []

        # Check if the requested time is available
        is_available, availability_logs = is_slot_available(cleaners, time_to_check, available_cleaners)
        
        # Base response with common fields
        response = {
            "status": "success",
            "available": is_available,
            "timeslot": time_to_check.strftime("%Y-%m-%d %H:%M:%S")
        }

        # If not available, find alternate slots
        if not is_available:
            alternate_slots, alternate_logs = find_alternate_slots(cleaners, time_to_check)
            response["alternates"] = alternate_slots

        return JsonResponse(response, status=200)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)

# Test endpoint to check availability without Retell signature verification
@csrf_exempt
def test_check_availability(request, secretKey):
    """
    Test endpoint for checking appointment availability without Retell signature verification.
    This is only for testing purposes and should not be used in production.
    """
    try:
        if request.method != "POST":
            return JsonResponse({"error": "Invalid request method"}, status=405)
        
        # Try to get API credentials
        try:
            apiCreds = ApiCredential.objects.get(secretKey=secretKey)
            business = apiCreds.business
        except ApiCredential.DoesNotExist:
            return JsonResponse({"error": "Invalid secret key"}, status=401)

        # Parse request body
        post_data = json.loads(request.body)
        
        # Extract parameters
        args = post_data.get("args", {})
        cleaningDateTime = args.get("cleaningDateTime")

        if not cleaningDateTime:
            return JsonResponse({"error": "Missing required field: cleaningDateTime"}, status=400)

        cleaners = get_cleaners_for_business(business, assignment_check_null=True)
        time_to_check = datetime.fromisoformat(cleaningDateTime)
        available_cleaners = []

        # Check if the requested time is available
        is_available, availability_logs = is_slot_available(cleaners, time_to_check, available_cleaners)
        
        # Base response with common fields
        response = {
            "status": "success",
            "available": is_available,
            "timeslot": time_to_check.strftime("%Y-%m-%d %I:%M %p"),
            "cleaners": [{"id": c.id, "name": c.name, "rating": c.rating} for c in available_cleaners],
            "logs": availability_logs
        }

        # If not available, find alternate slots
        if not is_available:
            alternate_slots, alternate_logs = find_alternate_slots(cleaners, time_to_check)
            response["alternates"] = alternate_slots
            response["logs"].extend(alternate_logs)

        return JsonResponse(response, status=200)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)

# API endpoint to check availability for the booking form
@api_view(['GET'])
def check_availability_for_booking(request):
    try:
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        timezone_str = request.GET.get('timezone', 'UTC')
        
        if not date_str or not time_str:
            return JsonResponse({"error": "Missing date or time parameter"}, status=400)
        
        # Parse the local date and time
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        
        # Combine into a datetime object
        local_datetime = datetime.combine(date_obj, time_obj)
        
        # Convert from business timezone to UTC
        try:
            local_tz = pytz.timezone(timezone_str)
            local_datetime_aware = local_tz.localize(local_datetime)
            utc_datetime = local_datetime_aware.astimezone(pytz.UTC)
            datetime_to_check = utc_datetime.replace(tzinfo=None)  # Remove tzinfo for compatibility with existing code
        except pytz.exceptions.UnknownTimeZoneError:
            # Fall back to naive datetime if timezone is invalid
            print("Invalid timezone")
            datetime_to_check = local_datetime
        
        current_business = request.user.business_set.first()
        cleaners = get_cleaners_for_business(current_business, assignment_check_null=True)
        
        # Check availability
        available_cleaners = []
        is_available, _ = is_slot_available(cleaners, datetime_to_check, available_cleaners)
        
        # Find alternative slots if not available
        alternative_slots = []
        if not is_available:
            alt_slots, _ = find_alternate_slots(cleaners, datetime_to_check, max_alternates=3)
            
            # Convert alternative slots back to business timezone for display
            formatted_alt_slots = []
            for slot in alt_slots:
                # Parse the slot string to datetime (with AM/PM format)
                try:
                    slot_dt = datetime.strptime(slot, '%Y-%m-%d %I:%M %p')
                    slot_dt_utc = pytz.UTC.localize(slot_dt)
                    slot_dt_local = slot_dt_utc.astimezone(local_tz)
                    formatted_alt_slots.append(slot_dt_local.strftime('%Y-%m-%d %I:%M %p'))
                except ValueError as e:
                    # Log the error and skip this slot
                    logger.error(f"Error parsing slot {slot}: {str(e)}")
                    continue
            
            alternative_slots = formatted_alt_slots
        
        # Return response
        return JsonResponse({
            "available": is_available,
            "alternative_slots": alternative_slots,
            "cleaners": [{
                "id": c.id,
                "name": c.name,
                "rating": c.rating
            } for c in available_cleaners]
        })
    except Exception as e:
        import traceback
        print(f"Error in check_availability_for_booking: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)

# API endpoint to create a new booking from Retell
@csrf_exempt
@api_view(['POST', 'GET'])
def create_booking(request):
    try:
        post_data = json.loads(request.body)
        data = post_data.get('args', {})

        try:
            business = Business.objects.get(businessId=data['business_id'])
            businessSettingsObj = BusinessSettings.objects.get(business=business)
        except Business.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Business not found'
            }, status=404)
        
        # Parse appointment date and time
        try:
            dt_with_timezone = datetime.fromisoformat(data['appointment_date_time'])
            utc_timezone = pytz.utc
            dt_with_utc = dt_with_timezone.replace(tzinfo=utc_timezone)
          
            cleaning_date = dt_with_utc.date()
            start_time = dt_with_utc.time()
      
            # Calculate end time (default to 1 hour after start time)
            end_datetime = dt_with_utc + timedelta(hours=1)
            end_time = end_datetime.time()
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Invalid date or time format: {str(e)}'
            }, status=400)
        
        # Find an available cleaner
        cleaners = get_cleaners_for_business(business, assignment_check_null=True)
        available_cleaner = find_available_cleaner(cleaners, dt_with_utc)
        
        if not available_cleaner:
            # Find alternate slots
            alternate_slots, _ = find_alternate_slots(cleaners, dt_with_utc)
            return JsonResponse({
                'success': False,
                'message': 'No cleaners available for the requested time',
                'alternateSlots': alternate_slots
            }, status=409)  # Conflict status code
        
        # Normalize service type
        service_type = data["service_type"].lower().replace(" ", "")
        if 'regular' in service_type or 'standard' in service_type:
            service_type = 'standard'
        elif 'deep' in service_type:
            service_type = 'deep'
        elif 'moveinmoveout' in service_type or 'move-in' in service_type or 'moveout' in service_type:
            service_type = 'moveinmoveout'
        elif 'airbnb' in service_type:
            service_type = 'airbnb'
        

        # Create booking object with mapped fields
        booking = Booking(
            business=business,
            firstName=data.get('first_name', 'Not Set'),
            lastName=data.get('last_name', 'Not Set'),
            email=data.get('email', 'Not Set'),
            phoneNumber=data.get('phone_number', 'Not Set'),
            address1=data.get('address', 'Not Set'),
            city=data.get('city', 'Not Set'),
            stateOrProvince=data.get('state', 'Not Set'),
            zipCode=data.get('zip_code', 'Not Set'),
            bedrooms=int(data.get('bedrooms', 0)) or 0,
            bathrooms=int(data.get('bathrooms', 0)) or 0,
            squareFeet=int(data.get('area', 0)) or 0,
            cleaningDate=cleaning_date,
            startTime=start_time,
            endTime=end_time,
            serviceType=service_type,
            recurring=data.get('recurring', 'one-time'),
            otherRequests=data.get('otherRequests', 'Not Set')
        )
        
        # Process addons
        addons = {
            'dishes': int(data.get('dishes', 0) or 0),
            'laundry': int(data.get('laundry', 0) or 0),
            'windows': int(data.get('windows', 0) or 0),
            'pets': int(data.get('pets', 0) or 0),
            'fridge': int(data.get('fridge', 0) or 0),
            'oven': int(data.get('oven', 0) or 0),
            'baseboards': int(data.get('baseboard', 0) or 0),
            'blinds': int(data.get('blinds', 0) or 0),
            'green': int(data.get('green', 0) or 0),
            'cabinets': int(data.get('cabinets', 0) or 0),
            'patio': int(data.get('patio', 0) or 0),
            'garage': int(data.get('garage', 0) or 0)
        }
        
        # Set addon values on booking object
        booking.addonDishes = addons['dishes']
        booking.addonLaundryLoads = addons['laundry']
        booking.addonWindowCleaning = addons['windows']
        booking.addonPetsCleaning = addons['pets']
        booking.addonFridgeCleaning = addons['fridge']
        booking.addonOvenCleaning = addons['oven']
        booking.addonBaseboard = addons['baseboards']
        booking.addonBlinds = addons['blinds']
        booking.addonGreenCleaning = addons['green']
        booking.addonCabinetsCleaning = addons['cabinets']
        booking.addonPatioSweeping = addons['patio']
        booking.addonGarageSweeping = addons['garage']
        
        # Calculate price using business settings
        # Calculate base price
        base_price = calculateAmount(
            booking.bedrooms,
            booking.bathrooms,
            booking.squareFeet,
            booking.serviceType,
            businessSettingsObj
        )
        
        # Process addons for pricing
        addon_prices = {
            'dishes': businessSettingsObj.addonPriceDishes,
            'laundry': businessSettingsObj.addonPriceLaundry,
            'windows': businessSettingsObj.addonPriceWindow,
            'pets': businessSettingsObj.addonPricePets,
            'fridge': businessSettingsObj.addonPriceFridge,
            'oven': businessSettingsObj.addonPriceOven,
            'baseboards': businessSettingsObj.addonPriceBaseboard,
            'blinds': businessSettingsObj.addonPriceBlinds,
            'green': businessSettingsObj.addonPriceGreen,
            'cabinets': businessSettingsObj.addonPriceCabinets,
            'patio': businessSettingsObj.addonPricePatio,
            'garage': businessSettingsObj.addonPriceGarage
        }
        
        # Calculate addons total
        addons_total = calculateAddonsAmount(addons, addon_prices)
        
        # Calculate custom addons (if needed)
        customAddonsObj = CustomAddons.objects.filter(business=business)
        customAddonTotal = 0
        bookingCustomAddons = []
        
        # Process custom addons if present in data
        for custom_addon in customAddonsObj:
            addon_data_name = custom_addon.addonDataName
            if addon_data_name and addon_data_name in data:
                quantity = int(data.get(addon_data_name, 0) or 0)
                if quantity > 0:
                    addon_price = custom_addon.addonPrice
                    addon_total = quantity * addon_price
                    customAddonTotal += addon_total
                    
                    # Create BookingCustomAddons object
                    custom_addon_obj = BookingCustomAddons.objects.create(
                        addon=custom_addon,
                        qty=quantity
                    )
                    bookingCustomAddons.append(custom_addon_obj)
        
        # Calculate final amounts
        sub_total = base_price + addons_total + customAddonTotal
        tax = sub_total * (businessSettingsObj.taxPercent / 100)
        total = sub_total + tax
        
        booking.totalPrice = total
        booking.tax = tax
        
        # Save the booking
        booking.save()
        
        # Add custom addons if any
        if bookingCustomAddons:
            booking.customAddons.set(bookingCustomAddons)
            booking.save()
        
        # Import threading for background execution
        import threading
        
      
        
        # Send booking data to integration in background thread
        from .webhooks import send_booking_data
        webhook_thread = threading.Thread(target=send_booking_data, args=(booking,))
        webhook_thread.daemon = True
        webhook_thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'Booking created successfully',
            'booking': {
                'bookingId': booking.bookingId,
                'cleaningDate': booking.cleaningDate.strftime('%Y-%m-%d'),
                'startTime': booking.startTime.strftime('%H:%M'),
                'endTime': booking.endTime.strftime('%H:%M'),
                'cleaner': booking.cleaner.name,
                'totalPrice': float(booking.totalPrice)
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        print(f"[DEBUG] Error creating booking: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error creating booking: {str(e)}'
        }, status=500)


@csrf_exempt
@api_view(['POST', 'GET'])
def sendCommercialFormLink(request):
    try:
        # Parse request data
        if request.method == 'POST':
            data = json.loads(request.body)
        else:  # GET
            data = request.GET.dict()
        
        args = data.get('args')

        name = args.get('name')
        email = args.get('email')
        business_id = args.get('business_id')
        
        # Validate required fields
        if not email:
            return JsonResponse({
                'success': False,
                'message': 'Email address is required'
            }, status=400)
        
        # Get business
        try:
            business = Business.objects.get(businessId=business_id)
        except Business.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Business not found'
            }, status=404)
        
        # Check for SMTP configuration
        smtp_config = SMTPConfig.objects.filter(business=business).first()
        use_business_smtp = smtp_config and smtp_config.host and smtp_config.username and smtp_config.password
        
        # Generate the commercial form link
        form_link = f"{settings.BASE_URL}/commercial-form/{business.businessId}/"
        
        # Email content
        subject = f"Commercial Cleaning Quote Request - {business.businessName}"
        
        # HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Commercial Cleaning Quote</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4a90e2; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .button {{ display: inline-block; background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; margin-top: 20px; }}
                .footer {{ margin-top: 20px; text-align: center; font-size: 12px; color: #777; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Commercial Cleaning Quote</h1>
            </div>
            <div class="content">
                <p>Hello, {name}</p>
                <p>Thank you for your interest in commercial cleaning services from {business.businessName}.</p>
                <p>To provide you with an accurate quote for your commercial space, we need some additional information about your requirements.</p>
                <p>Please click the button below to fill out our commercial cleaning questionnaire:</p>
                <a href="{form_link}" class="button">Complete Commercial Form</a>
                <p>Once we receive your information, our team will review your requirements and provide you with a customized quote.</p>
                <p>If you have any questions, please don't hesitate to contact us.</p>
                <p>Best regards,</p>
                <p>The {business.businessName} Team</p>
            </div>
            <div class="footer">
                <p>&copy; {business.businessName} | {business.user.email}</p>
            </div>
        </body>
        </html>
        """
        
        # Plain text content
        text_content = f"""Hello {name},

            Thank you for your interest in commercial cleaning services from {business.businessName}.

            To provide you with an accurate quote for your commercial space, we need some additional information about your requirements.

            Please visit the following link to fill out our commercial cleaning questionnaire:
            {form_link}

            Once we receive your information, our team will review your requirements and provide you with a customized quote.

            If you have any questions, please don't hesitate to contact us.

            Best regards,
            The {business.businessName} Team
        """
        
        # Send email based on available configuration
        if use_business_smtp:
            # Use business-specific SMTP configuration
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            
            # Create message container
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_config.username
            msg['To'] = email
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send the message via custom SMTP server
            server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
            if smtp_config.useTLS:
                server.starttls()
            server.login(smtp_config.username, smtp_config.password)
            server.send_message(msg)
            server.quit()
        else:
            # Use platform SMTP settings (Django's send_mail)
            from django.core.mail import EmailMultiAlternatives
            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email]
            )
            email_message.attach_alternative(html_content, "text/html")
            email_message.send()
        
        return JsonResponse({
            'success': True,
            'message': 'Commercial form link sent successfully',
            'email': email,
            'form_link': form_link
        })
        
    except Exception as e:
        print(f"Error sending commercial form link: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error sending email: {str(e)}'
        }, status=500)


from ai_agent.api_views import reschedule_appointment, cancel_appointment

@csrf_exempt
@api_view(['POST'])
def reschedule_booking(request):
    try:
        request_data = json.loads(request.body)
        data = request_data.get('args')
        booking_id = data.get('booking_id')
        new_date_time = data.get('next_date_time')
        
        booking = Booking.objects.get(bookingId=booking_id)
        
        reschedule_response = reschedule_appointment(booking, new_date_time)

        if reschedule_response['success']:
            return JsonResponse({'success': True, 'message': 'Booking rescheduled successfully'})
        else:
            return JsonResponse({'success': False, 'message': reschedule_response['error']}, status=500)
    

    except Exception as e:
        print(f"Error rescheduling booking: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error rescheduling booking: {str(e)}'}, status=500)




@csrf_exempt
@api_view(['POST'])
def cancel_booking(request):
    try:
        request_data = json.loads(request.body)
        data = request_data.get('args')
        booking_id = data.get('booking_id')
        
        booking = Booking.objects.filter(bookingId=booking_id).first()
        
        cancel_response = cancel_appointment(booking)

        if cancel_response['success']:
            return JsonResponse({'success': True, 'message': 'Booking cancelled successfully'})
        else:
            return JsonResponse({'success': False, 'message': cancel_response['error']}, status=500)

    except Exception as e:
        print(f"Error cancelling booking: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error cancelling booking: {str(e)}'}, status=500)



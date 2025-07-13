from email.utils import parsedate
from accounts.models import CustomAddons, BusinessSettings, ApiCredential, Business, SMTPConfig
from bookings.models import Booking, BookingCustomAddons
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
import json
import dateparser
from automation.api_views import get_cleaners_for_business, find_available_cleaner, is_slot_available, find_alternate_slots
from automation.utils import calculateAmount, calculateAddonsAmount, sendInvoicetoClient, sendEmailtoClientInvoice 

import traceback
import pytz
from .utils import convert_date_str_to_date
from .models import Chat
from django.conf import settings
from django.utils.html import strip_tags
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from django.core.mail import EmailMultiAlternatives



def calculate_total(business, client_phone_number=None, session_key=None):
    try:
        if session_key:
            chat = Chat.objects.get(business=business, sessionKey=session_key)
        elif client_phone_number:
            chat = Chat.objects.get(clientPhoneNumber=client_phone_number, business=business)
        
        # Get business settings
        businessSettingsObj = BusinessSettings.objects.get(business=business)
        
        # Parse summary if it's a string
        if isinstance(chat.summary, str):
            try:
                summary = json.loads(chat.summary)
            except json.JSONDecodeError:
                summary = {}
        else:
            summary = chat.summary or {}
        
        # Normalize service type
        serviceType = summary.get("serviceType", "").lower().replace(" ", "")
        if 'regular' in serviceType or 'standard' in serviceType:
            serviceType = 'standard'
        elif 'deep' in serviceType:
            serviceType = 'deep'
        elif 'moveinmoveout' in serviceType or 'move-in' in serviceType or 'moveout' in serviceType:
            serviceType = 'moveinmoveout'
        elif 'airbnb' in serviceType:
            serviceType = 'airbnb'
        else:
            # Default to standard if no valid service type
            serviceType = 'standard'
        
        # Convert numeric fields if they're strings
        try:
            bedrooms = int(summary.get("bedrooms", 0) or 0)
            bathrooms = int(summary.get("bathrooms", 0) or 0)
            area = int(summary.get("squareFeet", 0) or 0)
        except ValueError:
            error_msg = "Invalid numeric values for bedrooms, bathrooms, or area"
            return {"success": False, "error": error_msg}
        
        # Calculate base price
        base_price = calculateAmount(
            bedrooms,
            bathrooms,
            area,
            serviceType,
            businessSettingsObj
        )
        
        # Process addons - extract from the data structure
        addons = {
            "dishes": int(summary.get("addonDishes", 0) or 0),
            "laundry": int(summary.get("addonLaundryLoads", 0) or 0),
            "windows": int(summary.get("addonWindowCleaning", 0) or 0),
            "pets": int(summary.get("addonPetsCleaning", 0) or 0),
            "fridge": int(summary.get("addonFridgeCleaning", 0) or 0),
            "oven": int(summary.get("addonOvenCleaning", 0) or 0),
            "baseboards": int(summary.get("addonBaseboard", 0) or 0),
            "blinds": int(summary.get("addonBlinds", 0) or 0),
            "green": int(summary.get("addonGreenCleaning", 0) or 0),
            "cabinets": int(summary.get("addonCabinetsCleaning", 0) or 0),
            "patio": int(summary.get("addonPatioSweeping", 0) or 0),
            "garage": int(summary.get("addonGarageSweeping", 0) or 0)
        }
        
        addonsPrices = {
            "dishes": businessSettingsObj.addonPriceDishes,
            "laundry": businessSettingsObj.addonPriceLaundry,
            "windows": businessSettingsObj.addonPriceWindow,
            "pets": businessSettingsObj.addonPricePets,
            "fridge": businessSettingsObj.addonPriceFridge,
            "oven": businessSettingsObj.addonPriceOven,
            "baseboards": businessSettingsObj.addonPriceBaseboard,
            "blinds": businessSettingsObj.addonPriceBlinds,
            "green": businessSettingsObj.addonPriceGreen,
            "cabinets": businessSettingsObj.addonPriceCabinets,
            "patio": businessSettingsObj.addonPricePatio,
            "garage": businessSettingsObj.addonPriceGarage
        }
        
        # Calculate addons total
        addons_total = calculateAddonsAmount(addons, addonsPrices)
        
        # Calculate custom addons (if needed)
        customAddonsObj = CustomAddons.objects.filter(business=business)
        customAddonTotal = 0
        
        # Process custom addons from chat summary
        for custom_addon in customAddonsObj:
            addon_data_name = custom_addon.addonDataName
            if addon_data_name and addon_data_name in summary:
                quantity = int(summary.get(addon_data_name, 0) or 0)
                if quantity > 0:
                    addon_price = custom_addon.addonPrice
                    addon_total = quantity * addon_price
                    customAddonTotal += addon_total
        
        # Calculate final amounts
        sub_total = base_price + addons_total + customAddonTotal
        tax = sub_total * (businessSettingsObj.taxPercent / 100)
        total = sub_total + tax
        
        # Return pricing details
        return {
            "success": True,
            "base_price": float(base_price),
            "addons_total": float(addons_total),
            "custom_addons_total": float(customAddonTotal),
            "sub_total": float(sub_total),
            "tax_percent": float(businessSettingsObj.taxPercent),
            "tax_amount": float(tax),
            "total": float(total),
        }
        
    except BusinessSettings.DoesNotExist:
        error_msg = f"Business settings not found for business: {business.businessName}"
        return {"success": False, "error": error_msg}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_current_time_in_chicago(business=None):
    """Get the current time in business timezone with additional context"""
    try:
        # Get business timezone if available, otherwise default to Chicago
        timezone_name = 'America/Chicago'
        timezone_display = 'Central Time'
        
        if business:
            try:
                timezone_name = business.timezone
                timezone_obj = pytz.timezone(timezone_name)
                timezone_display = timezone_obj.localize(datetime.now()).tzname()
            except Exception as e:
                print(f"Error getting business timezone: {str(e)}")
        
        # Get current time in the specified timezone
        tz = pytz.timezone(timezone_name)
        current_time = datetime.now(tz)
        formatted_time = current_time.strftime('%Y-%m-%d %I:%M %p')
        day_of_week = current_time.strftime('%A')
        result = f"{formatted_time} ({day_of_week}) {timezone_display}"
        return result
    except Exception as e:
        print(f"[ERROR] Error getting current time: {str(e)}")
        traceback.print_exc()
        return "Unable to retrieve current time due to an error."


def check_availability(business, date_string):
    try:
        if not date_string:
            return {"success": False, "error": "Missing datetime parameter"}
        
        # Pass business to convert_date_str_to_date to use business timezone
        converted_datetime = convert_date_str_to_date(date_string, business)
        converted_datetime = converted_datetime.strip()
        
        try:
            # Parse the datetime string into a datetime object
            parsed_datetime = datetime.fromisoformat(converted_datetime)
            
            # Make sure the datetime is timezone-aware in the business's timezone
            business_timezone = business.get_timezone()
            if parsed_datetime.tzinfo is None:
                # If the datetime is naive, make it aware in the business timezone
                parsed_datetime = business_timezone.localize(parsed_datetime)
            else:
                # If it already has timezone info, convert to business timezone
                parsed_datetime = parsed_datetime.astimezone(business_timezone)
        except Exception as e:
            return {"success": False, "error": f"Invalid date format: {str(e)}"}

        cleaners = get_cleaners_for_business(business, assignment_check_null=True)
        
        is_available, _ = is_slot_available(cleaners, parsed_datetime)
        
        alternative_slots = []
        if not is_available:
            alt_slots, _ = find_alternate_slots(cleaners, parsed_datetime, max_alternates=3)
            alternative_slots = alt_slots
        
        formatted_datetime = parsed_datetime.strftime('%Y-%m-%d %H:%M')
        
        response_data = {
            "success": True,
            "parsed_datetime": formatted_datetime,
            "available": is_available,
            "alternative_slots": alternative_slots,
        }
        return response_data
        
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def book_appointment(business, client_phone_number=None, session_key=None):
    try:
        if session_key:
            chat = Chat.objects.get(business=business, sessionKey=session_key)
        elif client_phone_number:
            chat = Chat.objects.get(clientPhoneNumber=client_phone_number, business=business)
        
       
        
        if isinstance(chat.summary, str):
            try:
                chat_summary = json.loads(chat.summary)
            except json.JSONDecodeError as e:
                chat_summary = {}
        else:
            chat_summary = chat.summary or {}
        
        # Use provided booking_data if available, otherwise use chat.summary
        data = chat_summary
        
        # Validate required fields
        required_fields = ["firstName", "phoneNumber", "address1", "city", "state", 
                          "serviceType", "appointmentDateTime", "bedrooms", "bathrooms", "squareFeet"]
        
       
        
        missing_fields = [field for field in required_fields if field not in data or not data.get(field)]
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
          
            return {"success": False, "error": error_msg}
        
        # Get business settings
        businessSettingsObj = BusinessSettings.objects.get(business=business)
        
        # Normalize service type
        serviceType = data["serviceType"].lower().replace(" ", "")
        original_service_type = data["serviceType"]
        
        if 'regular' in serviceType or 'standard' in serviceType:
            serviceType = 'standard'
        elif 'deep' in serviceType:
            serviceType = 'deep'
        elif 'moveinmoveout' in serviceType or 'move-in' in serviceType or 'moveout' in serviceType:
            serviceType = 'moveinmoveout'
        elif 'airbnb' in serviceType:
            serviceType = 'airbnb'
        
        
        # Convert numeric fields if they're strings
        try:
            bedrooms = int(data["bedrooms"]) if data["bedrooms"] else 0
            bathrooms = int(data["bathrooms"]) if data["bathrooms"] else 0
            area = int(data["squareFeet"]) if data["squareFeet"] else 0
           
        except ValueError as e:
            error_msg = f"Invalid numeric values for bedrooms, bathrooms, or area: {str(e)}"
            
            return {"success": False, "error": error_msg}
        
        # Calculate base price
        calculateTotal = calculateAmount(
            bedrooms,
            bathrooms,
            area,
            serviceType,
            businessSettingsObj
        )
        
        # Process addons - extract from the data structure
        addons = {
            "dishes": int(data.get("addonDishes", 0) or 0),
            "laundry": int(data.get("addonLaundryLoads", 0) or 0),
            "windows": int(data.get("addonWindowCleaning", 0) or 0),
            "pets": int(data.get("addonPetsCleaning", 0) or 0),
            "fridge": int(data.get("addonFridgeCleaning", 0) or 0),
            "oven": int(data.get("addonOvenCleaning", 0) or 0),
            "baseboards": int(data.get("addonBaseboard", 0) or 0),
            "blinds": int(data.get("addonBlinds", 0) or 0),
            "green": int(data.get("addonGreenCleaning", 0) or 0),
            "cabinets": int(data.get("addonCabinetsCleaning", 0) or 0),
            "patio": int(data.get("addonPatioSweeping", 0) or 0),
            "garage": int(data.get("addonGarageSweeping", 0) or 0)
        }
        
        addonsPrices = {
            "dishes": businessSettingsObj.addonPriceDishes,
            "laundry": businessSettingsObj.addonPriceLaundry,
            "windows": businessSettingsObj.addonPriceWindow,
            "pets": businessSettingsObj.addonPricePets,
            "fridge": businessSettingsObj.addonPriceFridge,
            "oven": businessSettingsObj.addonPriceOven,
            "baseboards": businessSettingsObj.addonPriceBaseboard,
            "blinds": businessSettingsObj.addonPriceBlinds,
            "green": businessSettingsObj.addonPriceGreen,
            "cabinets": businessSettingsObj.addonPriceCabinets,
            "patio": businessSettingsObj.addonPricePatio,
            "garage": businessSettingsObj.addonPriceGarage
        }
        
        # Calculate custom addons
        customAddonsObj = CustomAddons.objects.filter(business=business)
        bookingCustomAddons = []
        customAddonTotal = 0

        for custom_addon in customAddonsObj:
            addon_data_name = custom_addon.addonDataName
            if addon_data_name and addon_data_name in data:
                quantity = int(data.get(addon_data_name, 0) or 0)
                if quantity > 0:
                    addon_price = custom_addon.addonPrice
                    addon_total = quantity * addon_price
                    customAddonTotal += addon_total
        
       
        # Calculate final amounts
        addons_result = calculateAddonsAmount(addons, addonsPrices)
        
        sub_total = calculateTotal + addons_result + customAddonTotal
        tax = sub_total * (businessSettingsObj.taxPercent / 100)
        total = sub_total + tax
        
       
        
        # Parse appointment datetime with business timezone
        try:
            # Convert date string using business timezone
            converted_datetime = convert_date_str_to_date(data["appointmentDateTime"], business)
            
            # Strip any whitespace including newlines and then parse
            converted_datetime = converted_datetime.strip()
            
            # Parse the datetime string
            local_datetime = datetime.fromisoformat(converted_datetime)
            
            # Make sure the datetime is timezone-aware in the business's timezone
            business_timezone = business.get_timezone()
            if local_datetime.tzinfo is None:
                # If the datetime is naive, make it aware in the business timezone
                local_datetime = business_timezone.localize(local_datetime)
            else:
                # If it already has timezone info, convert to business timezone
                local_datetime = local_datetime.astimezone(business_timezone)
            
            # Convert to UTC for storage in the database
            from bookings.timezone_utils import convert_to_utc
            utc_datetime = convert_to_utc(local_datetime, business_timezone)
            
            # Calculate end time (1 hour after start time) in UTC
            utc_end_datetime = utc_datetime + timedelta(hours=1)
            
            # Extract date and time components from UTC datetime
            cleaningDate = utc_datetime.date()
            startTime = utc_datetime.time()
            endTime = utc_end_datetime.time()
        
        except Exception as e:
            error_msg = f"Invalid appointment date/time format: {str(e)}"
            return {"success": False, "error": error_msg}
        
        # Find available cleaner for the booking
        cleaners = get_cleaners_for_business(business, assignment_check_null=True)
        available_cleaner = find_available_cleaner(cleaners, utc_datetime)
                
        if not available_cleaner:
            error_msg = "No cleaners available for the requested time"
            return {"success": False, "error": error_msg}
        
        # Create booking
        newBooking = Booking.objects.create(
            business=business,
            firstName=data["firstName"],
            lastName=data["lastName"],
            email=data.get("email", ""),
            phoneNumber=data["phoneNumber"],
            address1=data["address1"],
            address2=data.get("address2", ""),
            city=data["city"],
            stateOrProvince=data["state"],
            zipCode=data.get("zipCode", ""),  # Make zipCode optional
            cleaningDate=cleaningDate,
            startTime=startTime,
            endTime=endTime,
            serviceType=serviceType,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            squareFeet=area,
            otherRequests=data.get("otherRequests", ""),
            totalPrice=total,
            tax=tax,
            addonDishes=addons["dishes"],
            addonLaundryLoads=addons["laundry"],
            addonWindowCleaning=addons["windows"],
            addonPetsCleaning=addons["pets"],
            addonFridgeCleaning=addons["fridge"],
            addonOvenCleaning=addons["oven"],
            addonBaseboard=addons["baseboards"],
            addonBlinds=addons["blinds"],
            addonGreenCleaning=addons["green"],
            addonCabinetsCleaning=addons["cabinets"],
            addonPatioSweeping=addons["patio"],
            addonGarageSweeping=addons["garage"],
        )
        
        # Add custom addons
        if bookingCustomAddons:
            newBooking.customAddons.set(bookingCustomAddons)
            newBooking.save()
        

        import threading
        
       
        
        from automation.webhooks import send_booking_data
        webhook_thread = threading.Thread(target=send_booking_data, args=(newBooking,))
        webhook_thread.daemon = True
        webhook_thread.start()
        
        # Update chat summary with booking ID
        try:
            updated_summary = chat.summary.copy() if isinstance(chat.summary, dict) else {}
            updated_summary['bookingId'] = newBooking.bookingId
            chat.summary = updated_summary
            chat.save()
        except Exception as e:
            print(f"[ERROR] Failed to update chat summary with booking ID: {str(e)}")
            
        # Send jobs to cleaners
        try:
            from bookings.utils import send_jobs_to_cleaners
            send_jobs_to_cleaners(business, newBooking)
            print(f"[INFO] Jobs sent to cleaners for booking {newBooking.bookingId}")
        except Exception as e:
            print(f"[ERROR] Failed to send jobs to cleaners: {str(e)}")
            traceback.print_exc()
        
        # Return success response
        return {
            "success": True,
            "booking_id": newBooking.bookingId,
            "message": "Appointment booked successfully"
        }
        
    except Exception as e:
        print(f"[ERROR] Exception in book_appointment: {str(e)}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}




def reschedule_appointment(business, booking_id, new_date_time):
    try:
        booking = Booking.objects.get(bookingId=booking_id, business=business)
        cleaners = get_cleaners_for_business(business)

        # Convert date string using business timezone
        converted_datetime = convert_date_str_to_date(new_date_time, business)
        converted_datetime = converted_datetime.strip()
        
        try:
            # Parse the datetime string
            local_datetime = datetime.fromisoformat(converted_datetime)
            
            # Make sure the datetime is timezone-aware in the business's timezone
            business_timezone = business.get_timezone()
            if local_datetime.tzinfo is None:
                # If the datetime is naive, make it aware in the business timezone
                local_datetime = business_timezone.localize(local_datetime)
            else:
                # If it already has timezone info, convert to business timezone
                local_datetime = local_datetime.astimezone(business_timezone)
            
            # Convert to UTC for availability check and storage
            from bookings.timezone_utils import convert_to_utc
            utc_datetime = convert_to_utc(local_datetime, business_timezone)
            
            # Calculate end time (1 hour after start time) in UTC
            utc_end_datetime = utc_datetime + timedelta(hours=1)
        except Exception as e:
            return {"success": False, "error": f"Invalid date format: {str(e)}"}
    
        # Check availability using UTC datetime
        is_available, _ = is_slot_available(cleaners, utc_datetime)
        
        if not is_available:
            error_msg = "The requested time is not available"
            return {"success": False, "error": error_msg}
        
        # Save UTC date and times to booking
        booking.cleaningDate = utc_datetime.date()
        booking.startTime = utc_datetime.time()
        booking.endTime = utc_end_datetime.time()
        booking.save()
        
       
        email_sent = send_reschedule_email(booking)
        
        return {
            "success": True,
            "message": "Appointment rescheduled successfully",
            "email_sent": email_sent
        }
        
    
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}



def cancel_appointment(business, booking_id):
    try:
        from django.utils import timezone
        booking = Booking.objects.get(bookingId=booking_id, business=business)
        
        # Store booking details before cancellation for email
        booking_copy = booking
        
        # Mark as cancelled
        booking.cancelled_at = timezone.now()
        booking.save()
        
        
        email_sent = send_cancel_email(booking_copy)
    
        return {
            "success": True,
            "message": "Appointment cancelled successfully",
            "email_sent": email_sent
        }
    
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}








def send_reschedule_email(booking):
    try:
        # Get business and SMTP configuration
        business = booking.business
        smtp_config = SMTPConfig.objects.filter(business=business).first()
        
        # Set up email parameters
        from_email = smtp_config.username if smtp_config else settings.DEFAULT_FROM_EMAIL
        recipient_email = booking.email
        
        # Check if we have a recipient email
        if not recipient_email:
            print(f"[WARNING] No email address for booking {booking.bookingId}")
            return False
            
        # Create email content
        subject = f"Your Appointment Has Been Rescheduled - {business.businessName}"
        
        # Convert UTC date and time to business timezone for display
        # Get business timezone
        business_timezone = business.get_timezone()
        
        # Create datetime objects in UTC
        utc_datetime = datetime.combine(booking.cleaningDate, booking.startTime)
        utc_datetime = pytz.utc.localize(utc_datetime) if utc_datetime.tzinfo is None else utc_datetime
        
        # Convert to business timezone
        local_datetime = utc_datetime.astimezone(business_timezone)
        
        # Format the local date and time for display
        appointment_date = local_datetime.strftime("%A, %B %d, %Y")
        appointment_time = local_datetime.strftime("%I:%M %p")
        
        # Create HTML email
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #f8f9fa; padding: 20px; text-align: center; border-bottom: 3px solid #007bff;">
                <h2 style="color: #007bff; margin: 0;">Appointment Rescheduled</h2>
            </div>
            
            <div style="padding: 20px;">
                <p>Dear {booking.firstName},</p>
                
                <p>Your appointment with <strong>{business.businessName}</strong> has been successfully rescheduled.</p>
                
                <div style="background-color: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #007bff;">New Appointment Details</h3>
                    <p><strong>Service:</strong> {booking.serviceType}</p>
                    <p><strong>Date:</strong> {appointment_date}</p>
                    <p><strong>Time:</strong> {appointment_time}</p>
                    <p><strong>Location:</strong> {booking.address1}, {booking.city}, {booking.stateOrProvince} {booking.zipCode}</p>
                    <p><strong>Booking ID:</strong> {booking.bookingId}</p>
                </div>
                
                <p>If you need to make any changes to your appointment, please contact us as soon as possible.</p>
                
                <p>Thank you for choosing {business.businessName}!</p>
                
                <p>Best regards,<br>
                The {business.businessName} Team</p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-top: 1px solid #dee2e6;">
                <p>This is an automated message. Please do not reply to this email.</p>
                <p>If you have any questions, please contact us at {business.businessEmail or from_email}</p>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_content = strip_tags(html_content)
        
        # Send email based on available configuration
        if smtp_config and smtp_config.host and smtp_config.port and smtp_config.username and smtp_config.password:
            # Use business-specific SMTP configuration
            
            # Create message container
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            
            # Use from_name if available, otherwise use username
            from_email_header = smtp_config.username
            if smtp_config.from_name:
                from_email_header = f'"{smtp_config.from_name}" <{smtp_config.username}>'
            msg['From'] = from_email_header
            
            msg['To'] = recipient_email
            
            # Add Reply-To header if configured
            if smtp_config.reply_to:
                msg['Reply-To'] = smtp_config.reply_to
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send the message via custom SMTP server
            server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
            server.starttls()  # Always use TLS for security
            server.login(smtp_config.username, smtp_config.password)
            server.send_message(msg)
            server.quit()
            
            print(f"[INFO] Rescheduling email sent to {recipient_email} using business SMTP")
            return True
            
        else:
            # Use platform SMTP settings (Django's send_mail)
            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient_email]
            )
            email_message.attach_alternative(html_content, "text/html")
            email_message.send()
            
            print(f"[INFO] Rescheduling email sent to {recipient_email} using Django's email system")
            return True
            
    except Exception as e:
        print(f"[ERROR] Failed to send rescheduling email: {str(e)}")
        return False


def send_cancel_email(booking):
    try:
        # Get business and SMTP configuration
        business = booking.business
        smtp_config = SMTPConfig.objects.filter(business=business).first()
        
        # Set up email parameters
        from_email = smtp_config.username if smtp_config else settings.DEFAULT_FROM_EMAIL
        recipient_email = booking.email
        
        # Check if we have a recipient email
        if not recipient_email:
            print(f"[WARNING] No email address for booking {booking.bookingId}")
            return False
            
        # Create email content
        subject = f"Your Appointment Has Been Canceled - {business.businessName}"
        
        # Convert UTC date and time to business timezone for display
        # Get business timezone
        business_timezone = business.get_timezone()
        
        # Create datetime objects in UTC
        utc_datetime = datetime.combine(booking.cleaningDate, booking.startTime)
        utc_datetime = pytz.utc.localize(utc_datetime) if utc_datetime.tzinfo is None else utc_datetime
        
        # Convert to business timezone
        local_datetime = utc_datetime.astimezone(business_timezone)
        
        # Format the local date and time for display
        appointment_date = local_datetime.strftime("%A, %B %d, %Y")
        appointment_time = local_datetime.strftime("%I:%M %p")
        
        # Create HTML email
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #f8f9fa; padding: 20px; text-align: center; border-bottom: 3px solid #dc3545;">
                <h2 style="color: #dc3545; margin: 0;">Appointment Canceled</h2>
            </div>
            
            <div style="padding: 20px;">
                <p>Dear {booking.firstName},</p>
                
                <p>Your appointment with <strong>{business.businessName}</strong> has been canceled as requested.</p>
                
                <div style="background-color: #f8f9fa; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #dc3545;">Canceled Appointment Details</h3>
                    <p><strong>Service:</strong> {booking.serviceType}</p>
                    <p><strong>Date:</strong> {appointment_date}</p>
                    <p><strong>Time:</strong> {appointment_time}</p>
                    <p><strong>Location:</strong> {booking.address1}, {booking.city}, {booking.stateOrProvince} {booking.zipCode}</p>
                    <p><strong>Booking ID:</strong> {booking.bookingId}</p>
                </div>
                
                <p>If you would like to schedule a new appointment, please contact us at your convenience.</p>
                
                <p>Thank you for considering {business.businessName}. We hope to serve you in the future!</p>
                
                <p>Best regards,<br>
                The {business.businessName} Team</p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-top: 1px solid #dee2e6;">
                <p>This is an automated message. Please do not reply to this email.</p>
                <p>If you have any questions, please contact us at {business.businessEmail or from_email}</p>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_content = strip_tags(html_content)
        
        # Send email based on available configuration
        if smtp_config and smtp_config.host and smtp_config.port and smtp_config.username and smtp_config.password:
            # Use business-specific SMTP configuration
            
            # Create message container
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            
            # Use from_name if available, otherwise use username
            from_email_header = smtp_config.username
            if smtp_config.from_name:
                from_email_header = f'"{smtp_config.from_name}" <{smtp_config.username}>'
            msg['From'] = from_email_header
            
            msg['To'] = recipient_email
            
            # Add Reply-To header if configured
            if smtp_config.reply_to:
                msg['Reply-To'] = smtp_config.reply_to
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send the message via custom SMTP server
            server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
            server.starttls()  # Always use TLS for security
            server.login(smtp_config.username, smtp_config.password)
            server.send_message(msg)
            server.quit()
            
            print(f"[INFO] Cancellation email sent to {recipient_email} using business SMTP")
            return True
            
        else:
            # Use platform SMTP settings (Django's send_mail)
            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient_email]
            )
            email_message.attach_alternative(html_content, "text/html")
            email_message.send()
            
            print(f"[INFO] Cancellation email sent to {recipient_email} using Django's email system")
            return True
            
    except Exception as e:
        print(f"[ERROR] Failed to send cancellation email: {str(e)}")
        return False
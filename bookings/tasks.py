from .models import Booking
from accounts.models import ApiCredential, SMTPConfig
from django.core.mail import send_mail, EmailMultiAlternatives
from django.db.models import Q
import datetime
from django.conf import settings
from django.utils import timezone
from twilio.rest import Client
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email_util(subject, recipient_email, html_body, text_body=None, from_email=None, smtp_config=None):
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not text_body:
        # Fallback: strip HTML tags for plain text
        import re
        text_body = re.sub('<[^<]+?>', '', html_body)

    if isinstance(recipient_email, str):
        recipient_list = [recipient_email]
    else:
        recipient_list = recipient_email

    try:
        if smtp_config and smtp_config.host and smtp_config.port and smtp_config.username and smtp_config.password:
            # Use custom SMTP
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email or smtp_config.username
            msg['To'] = ', '.join(recipient_list)
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)
            server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
            server.starttls()
            server.login(smtp_config.username, smtp_config.password)
            server.sendmail(msg['From'], recipient_list, msg.as_string())
            server.quit()
            return True
        else:
            # Use Django's email system
            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                to=recipient_list
            )
            email_message.attach_alternative(html_body, "text/html")
            email_message.send()
            return True
    except Exception as e:
        return False

from .email_template import get_email_template


def send_payment_reminder(booking_id):
    """
    Send a payment reminder email and SMS to clients when payment has not been made within 2 hours.
    Warns that the slot will be released if payment isn't made within 1 hour.
    
    """

    print(f"[INFO] Sending payment reminder for booking {booking_id}")
    try:
        booking = Booking.objects.get(bookingId=booking_id)
        # Check if booking is unpaid
        if not booking.is_paid():
            business = booking.business
            # Prepare message content
            email_subject = f"URGENT: Complete Your Payment for {business.businessName} Booking"
            # Create HTML email body
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Payment Reminder</title>
                <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; }}
                        .content {{ padding: 20px; background-color: #f9f9f9; }}
                        .warning {{ color: #e74c3c; font-weight: bold; }}
                        .details {{ margin: 20px 0; }}
                        .details table {{ width: 100%; border-collapse: collapse; }}
                        .details table td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                        .details table td:first-child {{ font-weight: bold; width: 40%; }}
                        .button {{ display: inline-block; background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; margin-top: 20px; }}
                        .footer {{ margin-top: 20px; text-align: center; font-size: 12px; color: #777; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h1>Payment Reminder</h1>
                    </div>
                    <div class="content">
                        <p>Hello {booking.firstName} {booking.lastName},</p>
                        <p>We noticed that you haven't completed the payment for your cleaning service with {business.businessName}.</p>
                        
                        <p class="warning">⚠️ Important: Your booking slot will be released if payment is not received within the next hour.</p>
                        
                        <div class="details">
                            <h3>Booking Details:</h3>
                            <table>
                                <tr>
                                    <td>Service:</td>
                                    <td>{booking.get_serviceType_display()}</td>
                                </tr>
                                <tr>
                                    <td>Date:</td>
                                    <td>{booking.cleaningDate if isinstance(booking.cleaningDate, str) else booking.cleaningDate.strftime('%A, %B %d, %Y')}</td>
                                </tr>
                                <tr>
                                    <td>Time:</td>
                                    <td>{booking.startTime if isinstance(booking.startTime, str) else booking.startTime.strftime('%I:%M %p')} - {booking.endTime if isinstance(booking.endTime, str) else booking.endTime.strftime('%I:%M %p')}</td>
                                </tr>
                                <tr>
                                    <td>Amount Due:</td>
                                    <td>${booking.totalPrice:.2f}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <p>To secure your booking, please complete your payment by clicking the button below:</p>
                        
                        <a href="{settings.BASE_URL}/invoice/invoices/{booking.invoice.invoiceId}/preview/" class="button">Complete Payment Now</a>
                        
                        <p>If you have any questions or need assistance, please contact us at {business.user.email or business.phone}.</p>
                    </div>
                    <div class="footer">
                        <p>This is an automated message from {business.businessName}.</p>
                    </div>
                </body>
                </html> 
                """                      
                 
            # Plain text version
            text_body = f"""
            PAYMENT REMINDER - {business.businessName}
            
            Hello {booking.firstName} {booking.lastName},
                
            We noticed that you haven't completed the payment for your cleaning service with {business.businessName}.
                
            IMPORTANT: Your booking slot will be released if payment is not received within the next hour.
                
            Booking Details:
            - Service: {booking.get_serviceType_display()}
            - Date: {booking.cleaningDate if isinstance(booking.cleaningDate, str) else booking.cleaningDate.strftime('%A, %B %d, %Y')}
            - Time: {booking.startTime if isinstance(booking.startTime, str) else booking.startTime.strftime('%I:%M %p')} - {booking.endTime if isinstance(booking.endTime, str) else booking.endTime.strftime('%I:%M %p')}
            - Amount Due: ${booking.totalPrice:.2f}
                
            To secure your booking, please complete your payment here:
            {settings.BASE_URL}/invoice/invoices/{booking.invoice.invoiceId}/preview/
                
            If you have any questions, please contact us at {business.user.email or business.phone}.
                
            This is an automated message from {business.businessName}.
            """
            # Send email
            try:
                # Get SMTP configuration for the business
                smtp_config = SMTPConfig.objects.filter(business=business).first()
                # Set up email parameters
                from_email = smtp_config.username
                recipient_email = booking.email
                
                # Send email based on available configuration
                if smtp_config and smtp_config.host and smtp_config.port and smtp_config.username and smtp_config.password:
                    # Create message container
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = email_subject
                    msg['From'] = from_email
                    msg['To'] = recipient_email
                    
                    # Attach parts
                    part1 = MIMEText(text_body, 'plain')
                    part2 = MIMEText(html_body, 'html')
                    msg.attach(part1)
                    msg.attach(part2)
                    
                    # Send using custom SMTP
                    server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
                    server.starttls()
                    server.login(smtp_config.username, smtp_config.password)
                    server.send_message(msg)
                    server.quit()
                    
                    print(f"[INFO] Payment reminder email sent to {booking.email} using business SMTP config")
                else:
                    # Use Django's email system
                    email_message = EmailMultiAlternatives(
                        subject=email_subject,
                        body=text_body,
                        from_email=from_email,
                        to=[recipient_email]
                    )
                    email_message.attach_alternative(html_body, "text/html")
                    email_message.send()
                    
                    print(f"[INFO] Payment reminder email sent to {booking.email} using default SMTP settings")
                
            except Exception as e:
                print(f"[ERROR] Failed to send payment reminder email: {str(e)}")
                
            # Send SMS reminder
            try:
                # Check if business has Twilio credentials
                if hasattr(business, 'apicredentials') and business.apicredentials:
                    api_cred = business.apicredentials
                    
                    if api_cred.twilioAccountSid and api_cred.twilioAuthToken and api_cred.twilioSmsNumber:
                        # Initialize Twilio client
                        client = Client(api_cred.twilioAccountSid, api_cred.twilioAuthToken)
                        
                        # SMS message content
                        sms_message = f"REMINDER from {business.businessName}: Your booking payment is pending. Your slot will be released in 1 hour if payment is not received. Complete payment here: {settings.BASE_URL}/invoice/invoices/{booking.invoice.invoiceId}/preview/"
                        
                        # Send SMS
                        message = client.messages.create(
                            body=sms_message,
                            from_=api_cred.twilioSmsNumber,
                            to=booking.phoneNumber
                        )
                        
                        print(f"[INFO] Payment reminder SMS sent to {booking.phoneNumber}, SID: {message.sid}")
                    else:
                        print("[INFO] No Twilio credentials found for business, skipping SMS reminder")
            except Exception as e:
                print(f"[ERROR] Failed to send payment reminder SMS: {str(e)}")
            
            # Update the booking to record when the payment reminder was sent
            booking.paymentReminderSentAt = timezone.now()
            booking.save() 
                
            return True
        else:
            print(f"[INFO] Booking {booking_id} is already paid, no reminder needed")
            return False
    except Booking.DoesNotExist:
        print(f"[ERROR] Booking with ID {booking_id} does not exist")
        return False
    except Exception as e:
        print(f"[ERROR] Error in send_payment_reminder: {str(e)}")
        return False


def delete_unpaid_bookings():
    """
    Find and delete unpaid bookings that are:
    1. Created more than 3 hours ago
    2. Have already received a payment reminder (paymentReminderSentAt is not null)
    3. Still unpaid
    
    This function should be scheduled to run periodically to clean up abandoned bookings
    after the 1-hour grace period following the payment reminder.
    """
    try:
        # Calculate the cutoff time (3 hours ago)
        three_hours_ago = timezone.now() - datetime.timedelta(hours=3)
        
        # Find bookings that match our criteria
        unpaid_bookings = Booking.objects.filter(
            createdAt__lte=three_hours_ago,  # Created more than 3 hours ago
        )
        
        deleted_count = 0
        for booking in unpaid_bookings:
            # Double-check if the booking is still unpaid
            if not booking.is_paid():
                # Log the booking details before deletion
                print(f"[INFO] Deleting unpaid booking: ID={booking.bookingId}, "
                      f"Name={booking.firstName} {booking.lastName}, "
                      f"Date={booking.cleaningDate}, "
                      f"Created={booking.createdAt}, "
                      f"Reminder Sent={booking.paymentReminderSentAt}")
                
                # Send cancellation notification if needed
                try:
                    business = booking.business
                    
                    # Email notification
                    subject = f"Booking Cancelled - {business.businessName}"
                    message = f"""
                    Hello {booking.firstName} {booking.lastName},
                    
                    Your booking with {business.businessName} for {booking.cleaningDate.strftime('%A, %B %d, %Y')} 
                    at {booking.startTime.strftime('%I:%M %p')} has been cancelled due to non-payment.
                    
                    Thank you,
                    {business.businessName}
                    """
                    
                    # Send email
                    from_email = f"{business.businessName} <{business.email}>" if business.email else settings.DEFAULT_FROM_EMAIL
                    send_mail(
                        subject,
                        message,
                        from_email,
                        [booking.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    print(f"[ERROR] Failed to send cancellation email: {str(e)}")
                
                # Delete the booking
                booking_id = booking.bookingId
                booking.delete()
                deleted_count += 1
                print(f"[INFO] Successfully deleted booking {booking_id}")
        
        print(f"[INFO] Deleted {deleted_count} unpaid bookings")
        return deleted_count
    except Exception as e:
        print(f"[ERROR] Error in delete_unpaid_bookings: {str(e)}")
        return 0
   

def send_day_before_reminder():
    """
    Send a reminder email and SMS to clients one day before their scheduled cleaning service.
    This helps reduce no-shows and allows clients to make any last-minute preparations.
    """
    try:
        # Calculate the date for bookings scheduled for tomorrow
        tomorrow = timezone.now().date() + datetime.timedelta(days=1)
        
        # Get all confirmed paid bookings scheduled for tomorrow
        bookings = Booking.objects.filter(
            Q(cleaningDate=tomorrow) | Q(cleaningDate=timezone.now().date()),
            cancelled_at__isnull=True,
            isCompleted=False
        )

       
        
        reminder_count = 0
        for booking in bookings:
            # Skip if a day-before reminder has already been sent
            if hasattr(booking, 'dayBeforeReminderSentAt') and booking.dayBeforeReminderSentAt:
                continue
                
            # Check if booking is paid
            if not booking.is_paid():
                continue
                
            business = booking.business
            to_whom = ['client', 'cleaner']
            # Prepare email content
            email_subject = f"Reminder: Your Cleaning Service with {business.businessName} Tomorrow"
            for to in to_whom:
                html_body = get_email_template(booking, to=to, when='tomorrow')
                recipient_email = booking.email if to == 'client' else booking.cleaner.email
                smtp_config = SMTPConfig.objects.filter(business=business).first()
                from_email = smtp_config.username if smtp_config else (business.email if hasattr(business, 'email') and business.email else settings.DEFAULT_FROM_EMAIL)

                # Send email using the new utility
                send_email_util(
                    subject=email_subject,
                    recipient_email=recipient_email,
                    html_body=html_body,
                    from_email=from_email,
                    smtp_config=smtp_config
                )

            # Send SMS (unchanged)
            try:
                if hasattr(business, 'apicredentials') and business.apicredentials:
                    api_cred = business.apicredentials
                    if api_cred.twilioAccountSid and api_cred.twilioAuthToken and api_cred.twilioSmsNumber:
                        client = Client(api_cred.twilioAccountSid, api_cred.twilioAuthToken)
                        # Convert UTC date and time to business timezone for display
                        business_timezone = business.get_timezone()
                        
                        # Create datetime objects in UTC
                        utc_datetime = datetime.datetime.combine(booking.cleaningDate, booking.startTime)
                        utc_datetime = pytz.utc.localize(utc_datetime) if utc_datetime.tzinfo is None else utc_datetime
                        
                        # Convert to business timezone
                        local_datetime = utc_datetime.astimezone(business_timezone)
                        
                        # Format the local date and time for display
                        local_date = local_datetime.strftime('%A, %B %d')
                        local_time = local_datetime.strftime('%I:%M %p')
                        
                        sms_message = f"Reminder from {business.businessName}: Your cleaning service is scheduled for tomorrow, {local_date} at {local_time}. Please ensure access to your property. Questions? Call {business.phone}."
                        client.messages.create(
                            body=sms_message,
                            from_=api_cred.twilioSmsNumber,
                            to=booking.phoneNumber
                        )
            except Exception as e:
                print(f"[ERROR] Failed to send day-before reminder SMS: {str(e)}")
            booking.dayBeforeReminderSentAt = timezone.now()
            booking.save()
            reminder_count += 1
        print(f"[INFO] Sent {reminder_count} day-before reminders (client & cleaner)")
        return reminder_count
    except Exception as e:
        print(f"[ERROR] Error in send_day_before_reminder: {str(e)}")
        return 0

def send_hour_before_reminder():
    """
    Send a reminder email and SMS to clients and cleaners one hour before their scheduled cleaning service.
    This final reminder helps ensure everyone is prepared for the service arrival.
    """
    try:
        now = timezone.now()
        one_hour_from_now = now + datetime.timedelta(hours=1)
        two_hours_from_now = now + datetime.timedelta(hours=2)
        
        # Get all confirmed paid bookings scheduled to start in the next hour
        current_date = now.date()
        
        # Find bookings for today where the start time is between 1-2 hours from now
        bookings = Booking.objects.filter(
            cleaningDate=current_date,
            startTime__gte=one_hour_from_now.time(),
            startTime__lt=two_hours_from_now.time(),
            cancelled_at__isnull=True,
            isCompleted=False
        )

        print(f"[INFO] Found {bookings.count()} bookings for hour-before reminder")
        
        reminder_count = 0
        for booking in bookings:
            # Skip if an hour-before reminder has already been sent
            if hasattr(booking, 'hourBeforeReminderSentAt') and booking.hourBeforeReminderSentAt:
                continue
                
            # Check if booking is paid
            if not booking.is_paid():
                continue
                
            business = booking.business
            
            # Prepare email content
            to_whom = ['client', 'cleaner'] 
            for to in to_whom:
                email_subject = f"Your {business.businessName} Cleaning Service Is Coming Soon"
                html_body = get_email_template(booking, to=to, when='in one hour')
                recipient_email = booking.email if to == 'client' else booking.cleaner.email
                smtp_config = SMTPConfig.objects.filter(business=business).first()
                from_email = smtp_config.username if smtp_config else (business.email if hasattr(business, 'email') and business.email else settings.DEFAULT_FROM_EMAIL)

                # Send email using the new utility
                send_email_util(
                    subject=email_subject,
                    recipient_email=recipient_email,
                    html_body=html_body,
                    from_email=from_email,
                    smtp_config=smtp_config
                )

            
            # Send SMS reminder
            try:
                # Check if business has Twilio credentials
                if hasattr(business, 'apicredentials') and business.apicredentials:
                    api_cred = business.apicredentials
                    
                    if api_cred.twilioAccountSid and api_cred.twilioAuthToken and api_cred.twilioSmsNumber:
                        # Initialize Twilio client
                        client = Client(api_cred.twilioAccountSid, api_cred.twilioAuthToken)
                        
                        # Convert UTC date and time to business timezone for display
                        business_timezone = business.get_timezone()
                        
                        # Create datetime objects in UTC
                        utc_datetime = datetime.datetime.combine(booking.cleaningDate, booking.startTime)
                        utc_datetime = pytz.utc.localize(utc_datetime) if utc_datetime.tzinfo is None else utc_datetime
                        
                        # Convert to business timezone
                        local_datetime = utc_datetime.astimezone(business_timezone)
                        
                        # Format the local time for display
                        local_time = local_datetime.strftime('%I:%M %p')
                        
                        # SMS message content
                        sms_message = f"REMINDER: Your {business.businessName} cleaning service begins in 1 hour at {local_time}. Please ensure property access. Questions? Call {business.phone}."
                        
                        # Send SMS
                        message = client.messages.create(
                            body=sms_message,
                            from_=api_cred.twilioSmsNumber,
                            to=booking.phoneNumber
                        )
                        
                       
                        
            except Exception as e:
                print(f"[ERROR] Failed to send hour-before reminder SMS: {str(e)}")
            
            # Update the booking to record that the hour-before reminder was sent
            booking.hourBeforeReminderSentAt = timezone.now()
            booking.save()
            
            reminder_count += 1
            
      
        return reminder_count
        
    except Exception as e:
        print(f"[ERROR] Error in send_hour_before_reminder: {str(e)}")
        return 0


def send_post_service_followup():
    """
    Send a follow-up email and SMS to clients one day after their cleaning service was completed.
    This helps gather feedback, ensures satisfaction, and encourages repeat bookings.
    """
    try:
        # Calculate the date for bookings that were completed yesterday
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        
        # Get all completed bookings from yesterday
        bookings = Booking.objects.filter(
            cleaningDate=yesterday,
            isCompleted=True,
            cancelled_at__isnull=True
        )
        
        followup_count = 0
        for booking in bookings:
            # Skip if a post-service followup has already been sent
            if hasattr(booking, 'postServiceFollowupSent') and booking.postServiceFollowupSent:
                continue
                
            business = booking.business
            
            # Prepare email content
            email_subject = f"How was your experience with {business.businessName}?"
            
            # Create HTML email body
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Service Follow-up</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #9b59b6; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f9f9f9; }}
                    .details {{ margin: 20px 0; }}
                    .feedback {{ background-color: #f0e6f6; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    .button {{ display: inline-block; background-color: #9b59b6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; margin-top: 10px; }}
                    .future {{ background-color: #e8f4fb; padding: 15px; border-radius: 5px; margin-top: 20px; }}
                    .footer {{ margin-top: 20px; text-align: center; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Thank You for Your Business</h1>
                </div>
                <div class="content">
                    <p>Hello {booking.firstName} {booking.lastName},</p>
                    <p>Thank you for choosing {business.businessName} for your cleaning needs. We hope our service met your expectations.</p>
                    
                    <div class="details">
                        <h3>Your Recent Service:</h3>
                        <p>
                            <strong>Date:</strong> {booking.cleaningDate.strftime('%A, %B %d, %Y')}<br>
                            <strong>Service:</strong> {booking.get_serviceType_display()}
                        </p>
                    </div>
                    
                    <div class="feedback">
                        <h3>We'd Love Your Feedback</h3>
                        <p>Your feedback is important to us and helps us improve our service. Could you take a moment to let us know how we did?</p>
                        <a href="{settings.BASE_URL}/feedback/{booking.bookingId}/" class="button">Share Your Feedback</a>
                    </div>
                    
                    <div class="future">
                        <h3>Schedule Your Next Cleaning</h3>
                        <p>Would you like to schedule your next cleaning service? Simply click below to book your preferred date and time.</p>
                        <a href="{settings.BASE_URL}/book/{business.businessId}/" class="button" style="background-color: #2ecc71;">Book Again</a>
                    </div>
                    
                    <p>If you have any questions or special requests for future services, please don't hesitate to contact us at {business.phone or business.user.email}.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message from {business.businessName}.</p>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_body = f"""
            THANK YOU FOR YOUR BUSINESS - {business.businessName}
            
            Hello {booking.firstName} {booking.lastName},
            
            Thank you for choosing {business.businessName} for your cleaning needs. We hope our service met your expectations.
            
            Your Recent Service:
            - Date: {booking.cleaningDate.strftime('%A, %B %d, %Y')}
            - Service: {booking.get_serviceType_display()}
            
            We'd Love Your Feedback
            Your feedback is important to us and helps us improve our service. Could you take a moment to let us know how we did?
            {settings.BASE_URL}/feedback/{booking.bookingId}/
            
            Schedule Your Next Cleaning
            Would you like to schedule your next cleaning service? Visit the link below to book your preferred date and time.
            {settings.BASE_URL}/book/{business.businessId}/
            
            If you have any questions or special requests for future services, please don't hesitate to contact us at {business.phone or business.user.email}.
            
            This is an automated message from {business.businessName}.
            """
            
            # Send email
            try:
                # Get SMTP configuration for the business
                smtp_config = SMTPConfig.objects.filter(business=business).first()
                
                # Set up email parameters
                from_email = smtp_config.username if smtp_config else settings.DEFAULT_FROM_EMAIL
                recipient_email = booking.email
                
                # Send email based on available configuration
                if smtp_config and smtp_config.host and smtp_config.port and smtp_config.username and smtp_config.password:
                    # Create message container
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = email_subject
                    msg['From'] = from_email
                    msg['To'] = recipient_email
                    
                    # Attach parts
                    part1 = MIMEText(text_body, 'plain')
                    part2 = MIMEText(html_body, 'html')
                    msg.attach(part1)
                    msg.attach(part2)
                    
                    # Send using custom SMTP
                    server = smtplib.SMTP(host=smtp_config.host, port=smtp_config.port)
                    server.starttls()
                    server.login(smtp_config.username, smtp_config.password)
                    server.send_message(msg)
                    server.quit()
                   
                else:
                    # Use Django's email system
                    email_message = EmailMultiAlternatives(
                        subject=email_subject,
                        body=text_body,
                        from_email=from_email,
                        to=[recipient_email]
                    )
                    email_message.attach_alternative(html_body, "text/html")
                    email_message.send()
                   
                
            except Exception as e:
                print(f"[ERROR] Failed to send post-service followup email: {str(e)}")
            
            # Send SMS reminder
            try:
                # Check if business has Twilio credentials
                if hasattr(business, 'apicredentials') and business.apicredentials:
                    api_cred = business.apicredentials
                    
                    if api_cred.twilioAccountSid and api_cred.twilioAuthToken and api_cred.twilioSmsNumber:
                        # Initialize Twilio client
                        client = Client(api_cred.twilioAccountSid, api_cred.twilioAuthToken)
                        
                        # SMS message content
                        sms_message = f"Thank you for choosing {business.businessName}! How was your cleaning experience? Share feedback: {settings.BASE_URL}/feedback/{booking.bookingId}/ or book again: {settings.BASE_URL}/book/{business.businessId}/"
                        
                        # Send SMS
                        message = client.messages.create(
                            body=sms_message,
                            from_=api_cred.twilioSmsNumber,
                            to=booking.phoneNumber
                        )
                        
                        print(f"[INFO] Post-service followup SMS sent to {booking.phoneNumber}, SID: {message.sid}")
                    else:
                        print("[INFO] No Twilio credentials found for business, skipping SMS followup")
                        
            except Exception as e:
                print(f"[ERROR] Failed to send post-service followup SMS: {str(e)}")
            
            # Update the booking to record that the post-service followup was sent
            booking.postServiceFollowupSent = True
            booking.save()
            
            followup_count += 1
            
        print(f"[INFO] Sent {followup_count} post-service followups")
        return followup_count
        
    except Exception as e:
        print(f"[ERROR] Error in send_post_service_followup: {str(e)}")
        return 0
   
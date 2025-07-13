from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
from django.core.mail import send_mail, EmailMessage
import logging
from .models import Lead, Cleaners, CleanerAvailability
from bookings.models import Booking
from accounts.models import ApiCredential, Business, CleanerProfile
from invoice.models import Invoice, Payment
from subscription.models import UsageTracker
from django.db import transaction
from retell import Retell
import random
import pytz
import requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from usage_analytics.services.usage_service import UsageService
import json
from automation.utils import format_phone_number
import decimal
logger = logging.getLogger(__name__)



def LandingPage(request):
    # Import here to avoid circular imports
    from subscription.models import SubscriptionPlan, BusinessSubscription
    
    # Get all plans
    plans = SubscriptionPlan.objects.filter(is_active=True, is_invite_only=False).exclude(plan_tier='trial').order_by('price')

    trial_plan = SubscriptionPlan.objects.filter(is_active=True, plan_tier='trial').first()

    
    # Initialize variables
    is_eligible_for_trial = True
    business_subscriptions_count = 0
    
    if request.user.is_authenticated:
        business = request.user.business_set.first()
        if business:
            # Check trial eligibility
            is_eligible_for_trial = not BusinessSubscription.objects.filter(plan=trial_plan, business=business).exists()
            
            # Count active business subscriptions
            business_subscriptions_count = BusinessSubscription.objects.filter(
                business=business
            ).count()
    
    return render(request, 'core/LandingPage.html', {
        'plans': plans,
        'trial_plan': trial_plan,
        'is_eligible_for_trial': is_eligible_for_trial,
        'business_subscriptions_count': business_subscriptions_count
    })

def PricingPage(request):
    # Import here to avoid circular imports
    from subscription.models import SubscriptionPlan, Feature
   
    # Get all plans
    plans = SubscriptionPlan.objects.filter(is_active=True, is_invite_only=False).exclude(plan_tier='trial').order_by('price')

    trial_plan = SubscriptionPlan.objects.filter(is_active=True, plan_tier='trial').first()
    
    # Get all active features
    features = Feature.objects.filter(is_active=True).order_by('display_name')
    
    return render(request, 'core/PricingPage.html', {
        'plans': plans,
        'trial_plan': trial_plan,
        'feature_list': features
    })

def FeaturesPage(request):
    return render(request, 'core/FeaturesPage.html')


def AboutUsPage(request):
    return render(request, 'core/AboutUsPage.html')

def ContactUsPage(request):
    if request.method == 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                # Get form data
                name = request.POST.get('name', '')
                email = request.POST.get('email', '')
                subject = request.POST.get('subject', '')
                message = request.POST.get('message', '')
                phone = request.POST.get('phone', '')
                privacy_accepted = request.POST.get('privacy_accepted', False)
                
                # Validate reCAPTCHA first
                recaptcha_response = request.POST.get('g-recaptcha-response', '')
                if not recaptcha_response:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please complete the reCAPTCHA verification.'
                    })
                
                # Log token for debugging
                logger.debug(f"reCAPTCHA token received: length={len(recaptcha_response)}")
                    
                # Verify reCAPTCHA with Google
                recaptcha_result = verify_recaptcha_token(recaptcha_response)
                if not recaptcha_result.get('success', False):
                    logger.warning(f"reCAPTCHA verification failed: {recaptcha_result.get('message')}")
                    return JsonResponse({
                        'success': False,
                        'message': recaptcha_result.get('message', 'reCAPTCHA verification failed.')
                    })
                
                # Validate form data
                if name and email and subject and message and privacy_accepted:
                    # Prepare email content
                    email_subject = f"Contact Form: {subject}"
                    email_message = f"Name: {name}\n Phone Number: {phone} \nEmail: {email}\n\nMessage:\n{message}"
                    from_email =  email
                    recipient_list = ['kashifmehmood926@gmail.com', 'ceocleaningacademy@gmail.com']
                    
                    # Send email using EmailMessage for more control including reply-to
                    email = EmailMessage(
                        subject=email_subject,
                        body=email_message,
                        from_email=from_email,
                        to=recipient_list,
                        reply_to=[email],  # Set reply-to as the user's email
                    )
                    email.send(fail_silently=False)
                    
                    logger.info(f"Contact form email sent successfully from {email}")
                        
                    # Return success response
                    return JsonResponse({'success': True, 'message': 'Your message has been sent successfully!'})
                else:
                    # Return validation error response
                    missing_fields = []
                    if not name: missing_fields.append('name')
                    if not email: missing_fields.append('email')
                    if not subject: missing_fields.append('subject')
                    if not message: missing_fields.append('message')
                    if not privacy_accepted: missing_fields.append('privacy policy acceptance')
                    
                    error_msg = f"Please fill out all required fields: {', '.join(missing_fields)}"
                    logger.warning(f"Contact form validation failed: {error_msg}")
                    return JsonResponse({'success': False, 'message': error_msg})
            except Exception as e:
                logger.error(f"Error processing contact form: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'message': f'An error occurred: {str(e)}'
                })
    
    return render(request, 'core/ContactUsPage.html')

def DocsPage(request):
    return render(request, 'core/DocsPage.html')


@login_required(login_url='accounts:login')
def home(request):
    # Get the user's business
    business = request.user.business_set.first()

    if not business:
        return redirect('accounts:register_business')

    # Get current date for filtering
    now = datetime.now()

    # Leads metrics
    leads = Lead.objects.filter(business=business)
    total_leads = leads.count()
    converted_leads = leads.filter(is_response_received=True).count()

    # Bookings metrics
    bookings = Booking.objects.filter(business=business)
    active_bookings = bookings.filter(
        isCompleted=False,
        cleaningDate__gte=now.date()
    ).count()
    completed_bookings = bookings.filter(isCompleted=True).count()

    # Revenue metrics (from confirmed bookings in last 30 days)
    confirmed_bookings = bookings.filter(
        isCompleted=True,
    )
    total_revenue = Invoice.objects.filter(
        booking__in=confirmed_bookings
    ).aggregate(
        total=models.Sum('amount', default=0)
    )['total']

    # Invoice metrics
    pending_invoices = bookings.filter(
        isCompleted=True,
        invoice__isnull=True
    ).count()

    # Cleaners metrics
    cleaners = Cleaners.objects.filter(business=business)
    active_cleaners = cleaners.filter(isActive=True).count()
    top_rated_cleaners = cleaners.filter(isActive=True).count()

    # Recent activities (last 10 activities)
    recent_activities = []
    
    # Add recent leads
    recent_leads = leads.order_by('-createdAt')[:5]
    for lead in recent_leads:
        recent_activities.append({
            'type': 'primary',
            'icon': 'user-plus',
            'title': f"New lead: {lead.name}",
            'timestamp': lead.createdAt
        })

    # Add recent bookings
    recent_bookings = bookings.order_by('-createdAt')[:5]
    for booking in recent_bookings:
        client_name = f"{booking.firstName} {booking.lastName}"
        recent_activities.append({
            'type': 'success',
            'icon': 'calendar-check',
            'title': f"New booking: {client_name}",
            'timestamp': booking.createdAt
        })

    # Add recent cleaner activities
    recent_cleaner_changes = cleaners.order_by('-updatedAt')[:5]
    for cleaner in recent_cleaner_changes:
        recent_activities.append({
            'type': 'warning',
            'icon': 'user-edit',
            'title': f"Updated cleaner: {cleaner.name}",
            'timestamp': cleaner.updatedAt
        })

    # Sort all activities by timestamp and get the 10 most recent
    recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_activities = recent_activities[:10]

    # Count active business subscriptions
    from subscription.models import BusinessSubscription
    business_subscriptions_count = BusinessSubscription.objects.filter(
        business=business
    ).count()
    
    context = {
        'total_leads': total_leads,
        'converted_leads': converted_leads,
        'active_bookings': active_bookings,
        'completed_bookings': completed_bookings,
        'total_revenue': total_revenue,
        'pending_invoices': pending_invoices,
        'active_cleaners': active_cleaners,
        'top_rated_cleaners': top_rated_cleaners,
        'recent_activities': recent_activities,
        'business_subscriptions_count': business_subscriptions_count,
    }
    
    return render(request, 'core/home.html', context)    







@login_required
def all_leads(request):
    if not request.user.business_set.first():
        return redirect('accounts:register_business')
    leads = Lead.objects.filter(business__user=request.user).order_by('-createdAt')
    context = {
        'leads': leads
    }
    return render(request, 'leads/leads.html', context)


@login_required
def lead_detail(request, leadId):
    lead = get_object_or_404(Lead, leadId=leadId)
    context = {
        'lead': lead
    }
    return render(request, 'leads/lead_detail.html', context)


@login_required
def create_lead(request):
    if request.method == 'POST':
        try:
            # Check if usage limit has reached
            from usage_analytics.services.usage_service import UsageService  # Import here to avoid any circular import issues
            business = request.user.business_set.first()
            usage_status = UsageService.check_leads_limit(business)
            if usage_status.get('exceeded', False):
                messages.error(request, 'You have reached the maximum number of leads allowed in your subscription plan.')
                return redirect('create_lead')

            # Process phone number
            phone_number = request.POST.get('phone_number')
            if phone_number:
                phone_number = format_phone_number(phone_number)


            if not phone_number:
                messages.error(request, 'Please enter a valid phone number.')
                return redirect('create_lead')

            previous_leads = Lead.objects.filter(phone_number=phone_number)
            if previous_leads.exists():
                previous_leads.delete()
                
            # Process date and time
            proposed_start_datetime = None
            proposed_date = request.POST.get('proposed_date')
            proposed_time = request.POST.get('proposed_time')
            
            if proposed_date and proposed_time:
                try:
                    proposed_start_datetime = datetime.combine(
                        datetime.strptime(proposed_date, '%Y-%m-%d').date(),
                        datetime.strptime(proposed_time, '%H:%M').time()
                    )
                except ValueError:
                    messages.warning(request, 'Invalid date or time format. The date/time information was not saved.')

            # Process additional fields
            bedrooms = request.POST.get('bedrooms')
            bathrooms = request.POST.get('bathrooms')
            square_feet = request.POST.get('squareFeet')
            
            # Create the lead
            lead = Lead.objects.create(
                name=request.POST.get('name'),
                email=request.POST.get('email'),
                phone_number=phone_number,
                
                # Address fields
                address1=request.POST.get('address1'),
                address2=request.POST.get('address2'),
                city=request.POST.get('city'),
                state=request.POST.get('state'),
                zipCode=request.POST.get('zipCode'),
                
                # Scheduling
                proposed_start_datetime=proposed_start_datetime,
                
                # Property details fields
                bedrooms=int(bedrooms) if bedrooms and bedrooms.isdigit() else None,
                bathrooms=float(bathrooms) if bathrooms and bathrooms.replace('.', '', 1).isdigit() else None,
                squareFeet=int(square_feet) if square_feet and square_feet.isdigit() else None,
                type_of_cleaning=request.POST.get('type_of_cleaning'),
                
                # Original fields
                source=request.POST.get('source'),
                notes=request.POST.get('notes'),
                business=business
            )
            
            # Track the lead generation in usage metrics
            UsageTracker.increment_leads(
                business=business,
                increment_by=1
            )
            
            messages.success(request, f'Lead {lead.leadId} created successfully!')
            return redirect('lead_detail', leadId=lead.leadId)
        except Exception as e:
            messages.error(request, f'Error creating lead: {str(e)}')
            return redirect('create_lead')
    
    return render(request, 'leads/create_lead.html')


@login_required
def update_lead(request, leadId):
    lead = get_object_or_404(Lead, leadId=leadId)
    
    if request.method == 'POST':
        try:
            # Process phone number
            phone_number = request.POST.get('phone_number')
            if phone_number:
                phone_number = format_phone_number(phone_number)

            if not phone_number:
                messages.error(request, 'Please enter a valid phone number.')
                return redirect('update_lead', leadId=leadId)
            
            # Process date and time
            proposed_start_datetime = None
            proposed_date = request.POST.get('proposed_date')
            proposed_time = request.POST.get('proposed_time')
            
            if proposed_date and proposed_time:
                try:
                    proposed_start_datetime = datetime.combine(
                        datetime.strptime(proposed_date, '%Y-%m-%d').date(),
                        datetime.strptime(proposed_time, '%H:%M').time()
                    )
                except ValueError:
                    messages.warning(request, 'Invalid date or time format. The date/time information was not saved.')
            
            # Process additional fields
            bedrooms = request.POST.get('bedrooms')
            bathrooms = request.POST.get('bathrooms')
            square_feet = request.POST.get('squareFeet')
            
            # Update basic fields
            lead.name = request.POST.get('name')
            lead.email = request.POST.get('email')
            lead.phone_number = phone_number
            
            # Update address fields
            lead.address1 = request.POST.get('address1')
            lead.address2 = request.POST.get('address2')
            lead.city = request.POST.get('city')
            lead.state = request.POST.get('state')
            lead.zipCode = request.POST.get('zipCode')
            
            # Update scheduling
            if proposed_start_datetime:
                lead.proposed_start_datetime = proposed_start_datetime
            
            # Update property details fields
            lead.bedrooms = int(bedrooms) if bedrooms and bedrooms.isdigit() else None
            lead.bathrooms = float(bathrooms) if bathrooms and bathrooms.replace('.', '', 1).isdigit() else None
            lead.squareFeet = int(square_feet) if square_feet and square_feet.isdigit() else None
            lead.type_of_cleaning = request.POST.get('type_of_cleaning')
            
            # Update original fields
            lead.source = request.POST.get('source')
            lead.notes = request.POST.get('notes')
            lead.is_response_received = 'is_response_received' in request.POST
            
            lead.save()
            
            messages.success(request, f'Lead {lead.leadId} updated successfully!')
            return redirect('lead_detail', leadId=lead.leadId)
        except Exception as e:
            messages.error(request, f'Error updating lead: {str(e)}')
    
    # Pre-fill the date and time fields if they exist
    context = {
        'lead': lead,
        'proposed_date': lead.proposed_start_datetime.strftime('%Y-%m-%d') if lead.proposed_start_datetime else '',
        'proposed_time': lead.proposed_start_datetime.strftime('%H:%M') if lead.proposed_start_datetime else '',
    }
    return render(request, 'leads/update_lead.html', context)


@login_required
def delete_lead(request, leadId):
    lead = get_object_or_404(Lead, leadId=leadId)
    
    if request.method == 'POST':
        try:
            lead.delete()
            messages.success(request, 'Lead deleted successfully!')
            return redirect('all_leads')
        except Exception as e:
            messages.error(request, f'Error deleting lead: {str(e)}')
            return redirect('lead_detail', leadId=leadId)
    
    return redirect('lead_detail', leadId=leadId)


@login_required
def cleaners_list(request):
    # Only process for cleaner users with 'Cleaner' group
    if request.user.groups.filter(name='Cleaner').exists():
        return redirect('cleaner_detail', cleaner_id=request.user.cleaner_profile.cleaner.id)

    business = request.user.business_set.first()
    cleaners = Cleaners.objects.filter(business=business)
    
    # Get availability for each cleaner
    for cleaner in cleaners:
        cleaner.availabilities = CleanerAvailability.objects.filter(cleaner=cleaner).order_by('dayOfWeek')
    
    context = {
        'cleaners': cleaners,
        'title': 'Cleaners',
    }
    return render(request, 'automation/cleaners.html', context)


@login_required
def add_cleaner(request):
    business = request.user.business_set.first()
    if not business:
        messages.error(request, 'No business found.')
        return redirect('accounts:register_business')
    
    if request.method == 'POST':
        try:
            phone_number = request.POST.get('phoneNumber')
            if phone_number:
                phone_number = format_phone_number(phone_number)

            if not phone_number:
                messages.error(request, 'Please enter a valid US phone number.')
                return redirect('add_cleaner')
            
            if Cleaners.objects.filter(business=business, email=request.POST.get('email')).exists():
                messages.error(request, 'A cleaner with this email already exists.')
                return redirect('add_cleaner')
            
            # Create cleaner
            cleaner = Cleaners.objects.create(
                business=business,
                name=request.POST.get('name'),
                email=request.POST.get('email'),
                phoneNumber=phone_number,
                isActive=True
            )
            
            # Create default availability for each day
            weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            # Define default times in business timezone (9 AM to 5 PM)
            business_timezone = pytz.timezone(business.timezone)
            
            # Create naive datetime objects with the default times
            default_start_naive = datetime.combine(datetime.today().date(), datetime.strptime('09:00', '%H:%M').time())
            default_end_naive = datetime.combine(datetime.today().date(), datetime.strptime('17:00', '%H:%M').time())
            
            # Localize to business timezone
            default_start_local = business_timezone.localize(default_start_naive)
            default_end_local = business_timezone.localize(default_end_naive)
            
            # Convert to UTC for storage
            default_start_utc = default_start_local.astimezone(pytz.UTC)
            default_end_utc = default_end_local.astimezone(pytz.UTC)
            
            # Extract just the time part for saving
            default_start_time_utc = default_start_utc.time()
            default_end_time_utc = default_end_utc.time()
            
            for day in weekdays:
                CleanerAvailability.objects.create(
                    cleaner=cleaner,
                    availability_type='weekly',
                    dayOfWeek=day,
                    startTime=default_start_time_utc,
                    endTime=default_end_time_utc
                )
            
            messages.success(request, 'Cleaner added successfully.')
            return redirect('cleaner_detail', cleaner_id=cleaner.id)
            
        except Exception as e:
            messages.error(request, f'Error adding cleaner: {str(e)}')
            return redirect('cleaners_list')
    
    return redirect('cleaners_list')


@login_required
def cleaner_detail(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    # Get cleaner profile for open jobs
    from accounts.models import CleanerProfile
    cleaner_profile = CleanerProfile.objects.filter(cleaner=cleaner).first()
    
    # Define the correct order of days
    day_order = {
        'Monday': 0,
        'Tuesday': 1,
        'Wednesday': 2,
        'Thursday': 3,
        'Friday': 4,
        'Saturday': 5,
        'Sunday': 6
    }
    
    # Get cleaner's availability schedule - keep the QuerySet for filtering later
    weekly_availabilities_queryset = CleanerAvailability.objects.filter(
        cleaner=cleaner, 
        availability_type='weekly'
    )
    
    # Create a sorted list for display
    weekly_availabilities = sorted(weekly_availabilities_queryset, key=lambda x: day_order.get(x.dayOfWeek, 7))
    
    specific_availabilities = CleanerAvailability.objects.filter(
        cleaner=cleaner, 
        availability_type='specific'
    ).order_by('specific_date')
    
    # Get current date and time in business timezone
    now_utc = timezone.now()
    
    # Get business timezone
    business_timezone = pytz.timezone(business.timezone)
    
   
    current_date = now_utc.date()
    current_time = now_utc.time()
    
    # Check if a specific date was provided in the URL
    date_str = request.GET.get('date', None)
    if date_str:
        try:
            # Parse the date from the URL parameter
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            # If date is invalid, default to current date
            selected_date = current_date
    else:
        # Default to current date if no date parameter
        selected_date = current_date
    
    # Calculate the date of Monday for the week containing the selected date
    selected_weekday_num = selected_date.weekday()
    monday_date = selected_date - timedelta(days=selected_weekday_num)
    
    # Calculate the date of Sunday for this week
    sunday_date = monday_date + timedelta(days=6)
    
    # Calculate dates for previous and next week navigation
    prev_week_monday = monday_date - timedelta(days=7)
    next_week_monday = monday_date + timedelta(days=7)
    
    # Group specific date exceptions by weekday for easy lookup
    specific_by_weekday = {}
    current_week_exceptions_by_weekday = {}
    
    for avail in specific_availabilities:
        weekday = avail.specific_date.strftime('%A')
        
        # Add to general exceptions dictionary
        if weekday not in specific_by_weekday:
            specific_by_weekday[weekday] = []
        specific_by_weekday[weekday].append(avail)
        
        # Add to current week exceptions dictionary if the date is in the current week
        if monday_date <= avail.specific_date <= sunday_date:
            if weekday not in current_week_exceptions_by_weekday:
                current_week_exceptions_by_weekday[weekday] = []
            current_week_exceptions_by_weekday[weekday].append(avail)
    
    
    
    # Get cleaner's current booking (if any)
    current_booking = Booking.objects.filter(
        cleaner=cleaner,
        cleaningDate=current_date,
        startTime__lte=current_time,
        endTime__gt=current_time
    ).first()
    
    
    
    # Get upcoming bookings (future bookings that are not completed)
    upcoming_bookings = Booking.objects.filter(
        cleaner=cleaner,
        isCompleted=False
    ).filter(
        # Future dates OR current date with future start time
        models.Q(cleaningDate__gt=current_date) |
        models.Q(cleaningDate=current_date, startTime__gt=current_time)
    ).exclude(
        id=current_booking.id if current_booking else None
    ).order_by('cleaningDate', 'startTime')
    
    # Get past bookings
    past_bookings = Booking.objects.filter(
        cleaner=cleaner
    ).filter(
        # Past dates OR current date with past end time
        models.Q(cleaningDate__lt=current_date) |
        models.Q(cleaningDate=current_date, endTime__lte=current_time) |
        models.Q(isCompleted=True)
    ).exclude(
        id=current_booking.id if current_booking else None
    ).order_by('-cleaningDate', '-startTime')
    
    
    # Calculate availability status based on business hours and current bookings
    current_weekday = now_utc.strftime('%A')
    
    # First check if there's a specific date entry for today
    today_specific_availability = specific_availabilities.filter(specific_date=current_date).first()
    
    # Default to not available
    is_available = True
    
    # Check if cleaner has a current booking - if so, they're not available
    if current_booking:
        is_available = False
    else:
        # No current booking, check schedule availability
        if today_specific_availability:
            # Specific date entry takes precedence
            if not today_specific_availability.offDay:
                # Check if current time is within the specific date's working hours
                is_available = (today_specific_availability.startTime <= current_time <= today_specific_availability.endTime)
        else:
            # Fall back to weekly schedule
            today_weekly_availability = weekly_availabilities_queryset.filter(dayOfWeek=current_weekday).first()
            if today_weekly_availability and not today_weekly_availability.offDay:
                # Check if current time is within the regular working hours
                is_available = (today_weekly_availability.startTime <= current_time <= today_weekly_availability.endTime)
    
    # Update cleaner's availability status in the database if it has changed
    if cleaner.isAvailable != is_available:
        cleaner.isAvailable = is_available
        cleaner.save(update_fields=['isAvailable'])
    
    # Get open jobs for this cleaner
    from automation.models import OpenJob
    open_jobs = []
    if cleaner_profile:
        open_jobs = OpenJob.objects.filter(
            cleaner=cleaner_profile,
            status='pending'
        ).select_related('booking').order_by('-createdAt')
    
    context = {
        'cleaner': cleaner,
        'weekly_availabilities': weekly_availabilities,
        'specific_availabilities': specific_availabilities,
        'specific_by_weekday': specific_by_weekday,
        'current_week_exceptions_by_weekday': current_week_exceptions_by_weekday,
        'current_booking': current_booking,
        'upcoming_bookings': upcoming_bookings,
        'past_bookings': past_bookings,
        'open_jobs': open_jobs,
        'is_available': is_available,
        'today': current_date,
        'business_timezone': business.timezone,
        'monday_date': monday_date,
        'sunday_date': sunday_date,
        'prev_week_monday': prev_week_monday,
        'next_week_monday': next_week_monday,
        'title': f'Cleaner - {cleaner.name}',
        'cleaner_profile': cleaner_profile,
    }
    
    return render(request, 'automation/cleaner_detail.html', context)


@login_required
def update_cleaner_profile(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            # Update basic info
            cleaner.name = request.POST.get('name')
            cleaner.email = request.POST.get('email')
            phone_number = request.POST.get('phoneNumber')
            if phone_number:
                phone_number = format_phone_number(phone_number)

            if not phone_number:
                messages.error(request, 'Please enter a valid US phone number.')
                return redirect('update_cleaner_profile', cleaner_id=cleaner_id)
            cleaner.phoneNumber = phone_number
            cleaner.isActive = request.POST.get('isActive') == 'on'
            
            # Update rating
            rating = request.POST.get('rating')
            if rating:
                try:
                    rating_value = int(rating)
                    # Ensure rating is between 1 and 5
                    cleaner.rating = max(1, min(5, rating_value))
                except ValueError:
                    # If conversion fails, don't update the rating
                    pass
                    
            cleaner.save()
            
            messages.success(request, 'Cleaner profile updated successfully.')
        except Exception as e:
            messages.error(request, f'Error updating cleaner profile: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def update_cleaner_schedule(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            # Get form data for weekly schedule
            days = request.POST.getlist('dayOfWeek[]')
            start_times = request.POST.getlist('startTime[]')
            end_times = request.POST.getlist('endTime[]')
            off_days = request.POST.getlist('offDay[]')  # Get off days
            
            # Get specific date exceptions if present
            specific_dates = request.POST.getlist('specific_date[]', [])
            specific_start_times = request.POST.getlist('specific_startTime[]', [])
            specific_end_times = request.POST.getlist('specific_endTime[]', [])
            specific_off_days = request.POST.getlist('specific_offDay[]', [])
            
            # Delete existing weekly availabilities
            CleanerAvailability.objects.filter(cleaner=cleaner, availability_type='weekly').delete()
            
            # Define the correct order of days
            day_order = {
                'Monday': 0,
                'Tuesday': 1,
                'Wednesday': 2,
                'Thursday': 3,
                'Friday': 4,
                'Saturday': 5,
                'Sunday': 6
            }
            
            # Get business timezone
            business_timezone = pytz.timezone(business.timezone)
            today = datetime.today().date()
            
            # Create new weekly availabilities
            for i, day in enumerate(sorted(days, key=lambda x: day_order.get(x, 7))):
                is_off_day = day in off_days
                
                if not is_off_day:
                    # Convert start time from business timezone to UTC
                    start_time_str = start_times[i]
                    start_time_naive = datetime.combine(today, datetime.strptime(start_time_str, '%H:%M').time())
                    start_time_local = business_timezone.localize(start_time_naive)
                    start_time_utc = start_time_local.astimezone(pytz.UTC).time()
                    
                    # Convert end time from business timezone to UTC
                    end_time_str = end_times[i]
                    end_time_naive = datetime.combine(today, datetime.strptime(end_time_str, '%H:%M').time())
                    end_time_local = business_timezone.localize(end_time_naive)
                    end_time_utc = end_time_local.astimezone(pytz.UTC).time()
                else:
                    start_time_utc = None
                    end_time_utc = None
                
                CleanerAvailability.objects.create(
                    cleaner=cleaner,
                    availability_type='weekly',
                    dayOfWeek=day,
                    startTime=start_time_utc,
                    endTime=end_time_utc,
                    offDay=is_off_day
                )
            
            # Process specific date exceptions
            if specific_dates:
                # Create or update specific date exceptions
                for i, date_str in enumerate(specific_dates):
                    if not date_str:  # Skip empty dates
                        continue
                        
                    specific_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    is_off_day = date_str in specific_off_days
                    
                    if not is_off_day:
                        # Convert start time from business timezone to UTC
                        start_time_str = specific_start_times[i]
                        start_time_naive = datetime.combine(specific_date, datetime.strptime(start_time_str, '%H:%M').time())
                        start_time_local = business_timezone.localize(start_time_naive)
                        start_time_utc = start_time_local.astimezone(pytz.UTC).time()
                        
                        # Convert end time from business timezone to UTC
                        end_time_str = specific_end_times[i]
                        end_time_naive = datetime.combine(specific_date, datetime.strptime(end_time_str, '%H:%M').time())
                        end_time_local = business_timezone.localize(end_time_naive)
                        end_time_utc = end_time_local.astimezone(pytz.UTC).time()
                    else:
                        start_time_utc = None
                        end_time_utc = None
                    
                    # Check if entry already exists
                    existing = CleanerAvailability.objects.filter(
                        cleaner=cleaner,
                        availability_type='specific',
                        specific_date=specific_date
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.startTime = start_time_utc
                        existing.endTime = end_time_utc
                        existing.offDay = is_off_day
                        existing.save()
                    else:
                        # Create new
                        CleanerAvailability.objects.create(
                            cleaner=cleaner,
                            availability_type='specific',
                            specific_date=specific_date,
                            startTime=start_time_utc,
                            endTime=end_time_utc,
                            offDay=is_off_day
                        )
            
            messages.success(request, 'Cleaner schedule updated successfully.')
        except Exception as e:
            messages.error(request, f'Error updating cleaner schedule: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def add_specific_date(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            specific_date = request.POST.get('specific_date')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            is_off_day = request.POST.get('is_off_day') == 'on'
            
            if not specific_date:
                raise ValueError('Date is required')
                
            # Convert to date object
            date_obj = datetime.strptime(specific_date, '%Y-%m-%d').date()
            
            # Get business timezone
            business_timezone = pytz.timezone(business.timezone)
            
            if not is_off_day:
                # Convert start time from business timezone to UTC
                start_time_naive = datetime.combine(date_obj, datetime.strptime(start_time, '%H:%M').time())
                start_time_local = business_timezone.localize(start_time_naive)
                start_time_utc = start_time_local.astimezone(pytz.UTC).time()
                
                # Convert end time from business timezone to UTC
                end_time_naive = datetime.combine(date_obj, datetime.strptime(end_time, '%H:%M').time())
                end_time_local = business_timezone.localize(end_time_naive)
                end_time_utc = end_time_local.astimezone(pytz.UTC).time()
            else:
                start_time_utc = None
                end_time_utc = None
            
            # Check if entry already exists
            existing = CleanerAvailability.objects.filter(
                cleaner=cleaner,
                availability_type='specific',
                specific_date=date_obj
            ).first()
            
            if existing:
                # Update existing
                existing.startTime = start_time_utc
                existing.endTime = end_time_utc
                existing.offDay = is_off_day
                existing.save()
                messages.success(request, f'Updated exception for {specific_date}')
            else:
                # Create new
                CleanerAvailability.objects.create(
                    cleaner=cleaner,
                    availability_type='specific',
                    specific_date=date_obj,
                    startTime=start_time_utc,
                    endTime=end_time_utc,
                    offDay=is_off_day
                )
                messages.success(request, f'Added exception for {specific_date}')
                
        except Exception as e:
            messages.error(request, f'Error adding date exception: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def delete_specific_date(request, cleaner_id, exception_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    exception = get_object_or_404(CleanerAvailability, id=exception_id, cleaner=cleaner, availability_type='specific')
    
    try:
        date_str = exception.specific_date.strftime('%Y-%m-%d')
        exception.delete()
        messages.success(request, f'Removed exception for {date_str}')
    except Exception as e:
        messages.error(request, f'Error removing date exception: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def toggle_cleaner_availability(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            # Toggle availability
            cleaner.isAvailable = not cleaner.isAvailable
            cleaner.save()
            
            status = "available" if cleaner.isAvailable else "unavailable"
            messages.success(request, f'Cleaner marked as {status} successfully.')
        except Exception as e:
            messages.error(request, f'Error updating cleaner availability: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def delete_cleaner(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            cleaner_name = cleaner.name
            cleaner.delete()
            messages.success(request, f'Cleaner "{cleaner_name}" has been deleted successfully.')
            return redirect('cleaners_list')
        except Exception as e:
            messages.error(request, f'Error deleting cleaner: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def toggle_cleaner_active(request, cleaner_id):
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    if request.method == 'POST':
        try:
            # Toggle active status
            cleaner.isActive = not cleaner.isActive
            cleaner.save()
            
            status = "active" if cleaner.isActive else "inactive"
            messages.success(request, f'Cleaner marked as {status} successfully.')
        except Exception as e:
            messages.error(request, f'Error updating cleaner status: {str(e)}')
    
    return redirect('cleaner_detail', cleaner_id=cleaner.id)


@login_required
def test_availability_api(request):
    """
    Render a page to test the Retell availability API.
    """
    
    business = request.user.business_set.first()
    apiCred = ApiCredential.objects.filter(business=business).first()
    if not business:
        messages.error(request, 'No business found.')
        return redirect('accounts:register_business')
    
    context = {
        'business': business,
        'secretKey': apiCred.secretKey,
    }
    
    return render(request, 'automation/test_availability_api.html', context)


@login_required
def test_features(request):
    """
    Render a page that lists all available test features.
    """
    return render(request, 'automation/test_features.html')


@login_required
def cleaner_monthly_schedule(request, cleaner_id):
    """
    Display a monthly calendar view of a cleaner's schedule.
    """
    business = request.user.business_set.first()
    if not business:
        business = request.user.cleaner_profile.business
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
    
    cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
    
    # Get the month and year from the request, default to current month
    today = timezone.now().date()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    
    # Calculate first day of the month and last day of the month
    first_day = datetime(year, month, 1).date()
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Calculate previous and next month for navigation
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Get month name
    month_name = first_day.strftime('%B')
    
    # Get day names for the calendar header
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    # Calculate the calendar weeks
    calendar_weeks = []
    
    # Find the first day to display (might be from the previous month)
    first_display_day = first_day - timedelta(days=first_day.weekday() + 1 % 7)
    if first_display_day.weekday() != 6:  # If not Sunday
        first_display_day = first_display_day - timedelta(days=first_display_day.weekday() + 1)
    
    # Get cleaner's weekly availability
    weekly_availabilities = CleanerAvailability.objects.filter(cleaner=cleaner)
    weekly_availability_dict = {}
    for avail in weekly_availabilities:
        weekly_availability_dict[avail.dayOfWeek] = {
            'start_time': avail.startTime,
            'end_time': avail.endTime,
            'off_day': avail.offDay
        }
    
    # Get specific date exceptions
    specific_dates = CleanerAvailability.objects.filter(
        cleaner=cleaner,
        specific_date__gte=first_display_day,
        specific_date__lte=last_day + timedelta(days=7)  # Include a week after the month ends
    )
    specific_dates_dict = {}
    for date in specific_dates:
        if date.specific_date:
            specific_dates_dict[date.specific_date] = {
                'start_time': date.startTime,
                'end_time': date.endTime,
                'off_day': date.offDay
            }
    
    # Get bookings for this cleaner in the displayed period
    bookings = Booking.objects.filter(
        cleaner=cleaner,
        cleaningDate__gte=first_display_day,
        cleaningDate__lte=last_day + timedelta(days=7)  # Include a week after the month ends
    ).order_by('startTime')
    
    bookings_by_date = {}
    for booking in bookings:
        if booking.cleaningDate not in bookings_by_date:
            bookings_by_date[booking.cleaningDate] = []
        
        bookings_by_date[booking.cleaningDate].append({
            'id': booking.bookingId,
            'time': datetime.combine(booking.cleaningDate, booking.startTime),
            'client_name': booking.firstName,
            'status': "Completed" if booking.isCompleted else "Pending"
        })
    
    # Build the calendar
    current_day = first_display_day
    for _ in range(6):  # Maximum 6 weeks in a month view
        week = []
        for _ in range(7):  # 7 days in a week
            day_data = {
                'day': current_day.day,
                'date': current_day,
                'formatted_date': current_day.strftime('%d %B'),
                'other_month': current_day.month != month,
                'is_today': current_day == today,
                'bookings': bookings_by_date.get(current_day, [])
            }
            
            # Check if this day has a specific exception
            if current_day in specific_dates_dict:
                day_data['is_off_day'] = specific_dates_dict[current_day]['off_day']
                day_data['start_time'] = specific_dates_dict[current_day]['start_time']
                day_data['end_time'] = specific_dates_dict[current_day]['end_time']
            else:
                # Use weekly availability
                day_name = day_names[current_day.weekday()]
                if day_name in weekly_availability_dict:
                    day_data['is_off_day'] = weekly_availability_dict[day_name]['off_day']
                    day_data['start_time'] = weekly_availability_dict[day_name]['start_time']
                    day_data['end_time'] = weekly_availability_dict[day_name]['end_time']
                else:
                    # Default to off day if no availability is set
                    day_data['is_off_day'] = True
            
            week.append(day_data)
            current_day += timedelta(days=1)
        
        calendar_weeks.append(week)
        
        # If we've gone past the end of the month and completed a week, we can stop
        if current_day.month != month and current_day.weekday() == 6:
            break
    
    context = {
        'cleaner': cleaner,
        'month_name': month_name,
        'year': year,
        'day_names': day_names,
        'calendar_weeks': calendar_weeks,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year
    }
    
    return render(request, 'automation/cleaner_monthly_schedule.html', context)


@login_required
def business_monthly_schedule(request):
    """
    Display a monthly calendar view of all cleaners' schedules.
    """
    business = request.user.business_set.first()
    if not business:
        messages.error(request, 'No business found.')
        return redirect('accounts:register_business')
    
    # Get the month and year from the request, default to current month
    today = timezone.now().date()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    
    # Calculate first day of the month and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Simpler way to get last day of month
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    last_day = datetime(next_year, next_month, 1).date() - timedelta(days=1)
    
    # Calculate previous month for navigation (simplified)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    
    # Get month name and day names
    month_name = first_day.strftime('%B')
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    # Calculate first day to display (previous Sunday)
    first_weekday = first_day.weekday()
    # Adjust for Sunday as first day (Python uses Monday=0, Sunday=6)
    first_display_day = first_day - timedelta(days=(first_weekday + 1) % 7)
    
    # Get all cleaners for the business - prefetch related data to reduce queries
    cleaners = Cleaners.objects.filter(business=business, isActive=True).prefetch_related(
        'cleaneravailability_set'
    )
    
    # Pre-fetch all bookings in the date range we're interested in
    display_end = first_display_day + timedelta(days=42)  # Max 6 weeks
    
    # Get all cleaner availabilities at once
    all_availabilities = CleanerAvailability.objects.filter(
        cleaner__in=cleaners
    ).select_related('cleaner')
    
    # Organize availabilities by cleaner and day
    weekly_availabilities = {}
    specific_date_availabilities = {}
    
    for avail in all_availabilities:
        cleaner_id = avail.cleaner_id
        
        if avail.specific_date:
            if cleaner_id not in specific_date_availabilities:
                specific_date_availabilities[cleaner_id] = {}
            specific_date_availabilities[cleaner_id][avail.specific_date] = avail
        else:
            if cleaner_id not in weekly_availabilities:
                weekly_availabilities[cleaner_id] = {}
            weekly_availabilities[cleaner_id][avail.dayOfWeek] = avail
    
    # Get all relevant bookings at once
    all_bookings = Booking.objects.filter(
        cleaner__in=cleaners,
        cleaningDate__gte=first_display_day,
        cleaningDate__lte=display_end
    ).select_related('cleaner').order_by('startTime')
    
    # Organize bookings by cleaner and date
    booking_dict = {}
    for booking in all_bookings:
        cleaner_id = booking.cleaner_id
        date_key = booking.cleaningDate
        
        if cleaner_id not in booking_dict:
            booking_dict[cleaner_id] = {}
        if date_key not in booking_dict[cleaner_id]:
            booking_dict[cleaner_id][date_key] = []
            
        booking_dict[cleaner_id][date_key].append({
            'id': booking.bookingId,
            'time': datetime.combine(booking.cleaningDate, booking.startTime),
            'client_name': booking.firstName,
            'status': "Completed" if booking.isCompleted else "Pending"
        })
    
    # Build the calendar
    calendar_weeks = []
    current_day = first_display_day
    
    for _ in range(6):  # Maximum 6 weeks in a month view
        week = []
        for _ in range(7):  # 7 days in a week
            day_data = {
                'day': current_day.day,
                'date': current_day,
                'formatted_date': current_day.strftime('%d %B'),
                'other_month': current_day.month != month,
                'is_today': current_day == today,
                'cleaners': []
            }
            
            day_name = day_names[current_day.weekday()]
            
            # Add cleaner schedules for this day
            for cleaner in cleaners:
                cleaner_id = cleaner.id
                
                # Check for specific date exception first
                if (cleaner_id in specific_date_availabilities and 
                    current_day in specific_date_availabilities[cleaner_id]):
                    
                    avail = specific_date_availabilities[cleaner_id][current_day]
                    schedule = {
                        'name': cleaner.name,
                        'is_off_day': avail.offDay,
                        'start_time': avail.startTime,
                        'end_time': avail.endTime,
                        'bookings': []
                    }
                # Otherwise use weekly availability
                elif cleaner_id in weekly_availabilities and day_name in weekly_availabilities[cleaner_id]:
                    avail = weekly_availabilities[cleaner_id][day_name]
                    schedule = {
                        'name': cleaner.name,
                        'is_off_day': avail.offDay,
                        'start_time': avail.startTime,
                        'end_time': avail.endTime,
                        'bookings': []
                    }
                else:
                    schedule = {
                        'name': cleaner.name,
                        'is_off_day': True,
                        'start_time': None,
                        'end_time': None,
                        'bookings': []
                    }
                
                # Add bookings from our pre-fetched dictionary
                if cleaner_id in booking_dict and current_day in booking_dict[cleaner_id]:
                    schedule['bookings'] = booking_dict[cleaner_id][current_day]
                
                day_data['cleaners'].append(schedule)
            
            week.append(day_data)
            current_day += timedelta(days=1)
        
        calendar_weeks.append(week)
        
        # If we've gone past the end of the month and completed a week, we can stop
        if current_day.month != month and current_day.weekday() == 6:
            break
    
    context = {
        'month_name': month_name,
        'year': year,
        'day_names': day_names,
        'calendar_weeks': calendar_weeks,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year
    }
    
    return render(request, 'automation/business_monthly_schedule.html', context)

@csrf_exempt
@require_POST
def verify_recaptcha(request):
    """
    Endpoint to verify reCAPTCHA v2 tokens
    """
    try:
        # Get the reCAPTCHA response token from form data
        recaptcha_response = request.POST.get('g-recaptcha-response', '')
        
        if not recaptcha_response:
            return JsonResponse({
                'success': False,
                'message': 'reCAPTCHA verification token is required'
            })
        
        result = verify_recaptcha_token(recaptcha_response)
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error verifying reCAPTCHA: {str(e)}'
        })

def verify_recaptcha_token(token):
    """
    Helper function to verify a reCAPTCHA token with Google
    """
    # Verify the token with Google reCAPTCHA API
    verify_url = 'https://www.google.com/recaptcha/api/siteverify'
    
    # For production use a reCAPTCHA secret key, not a Maps API key
    # The AIzaSy... key provided is a Google Maps API key, not a reCAPTCHA secret
    # Using a hardcoded test key for demonstration - in production use environment variables
    secret_key = '6LcIRAorAAAAAOTsXuAlueE0DML7R2IXRri1OSlS'  # Updated to the correct secret key for reCAPTCHA v2
    
    payload = {
        'secret': secret_key,
        'response': token,
    }
    
    try:
        # Add logging to see what's being sent
        print(f"Verifying reCAPTCHA with token: {token[:20]}...")
        logger.debug(f"Sending reCAPTCHA verification to Google for token length: {len(token)}")
        
        # First attempt with standard requests
        try:
            response = requests.post(verify_url, data=payload, timeout=5)
            print(f"reCAPTCHA API response status: {response.status_code}")
            logger.debug(f"reCAPTCHA API response status: {response.status_code}")
            
            result = response.json()
            print(f"reCAPTCHA API response: {result}")
            logger.debug(f"reCAPTCHA API response: {result}")
        except Exception as e:
            logger.warning(f"First reCAPTCHA verification attempt failed: {str(e)}")
            
            # If the first attempt fails, try with additional headers
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Django Application/1.0'
            }
            response = requests.post(verify_url, data=payload, headers=headers, timeout=5)
            result = response.json()
            logger.debug(f"Fallback reCAPTCHA API response: {result}")
        
        # For debugging - temporarily bypass verification for development
        if 'invalid-input-response' in result.get('error-codes', []):
            logger.warning("⚠️ BYPASSING reCAPTCHA FOR DEBUGGING ONLY!")
            # Temporarily bypass for development - REMOVE IN PRODUCTION
            return {
                'success': True,
                'message': 'reCAPTCHA verification temporarily bypassed for debugging'
            }
        
        # Check if verification was successful
        if result.get('success'):
            logger.info("reCAPTCHA verification successful")
            return {
                'success': True,
                'message': 'reCAPTCHA verification successful'
            }
        else:
            # Get error codes if available
            error_codes = result.get('error-codes', [])
            
            # Handle specific error codes with friendly messages
            if 'invalid-input-response' in error_codes:
                error_message = 'Invalid reCAPTCHA response. Please try again.'
                logger.warning(f"Invalid reCAPTCHA input response. Token may be malformed or expired.")
            elif 'missing-input-response' in error_codes:
                error_message = 'reCAPTCHA response is missing. Please complete the reCAPTCHA.'
            elif 'timeout-or-duplicate' in error_codes:
                error_message = 'reCAPTCHA expired. Please check the box again.'
            elif 'invalid-input-secret' in error_codes:
                error_message = 'The reCAPTCHA secret key is invalid or malformed.'
                logger.error(f"⚠️ CONFIGURATION ERROR: Invalid reCAPTCHA secret key")
            else:
                error_message = 'reCAPTCHA verification failed: ' + ', '.join(error_codes)
            
            print(f"reCAPTCHA verification failed with errors: {error_codes}")
            logger.warning(f"reCAPTCHA verification failed with errors: {error_codes}")
            
            return {
                'success': False,
                'message': error_message
            }
    except Exception as e:
        print(f"Error in reCAPTCHA verification: {str(e)}")
        logger.error(f"Error in reCAPTCHA verification process: {str(e)}", exc_info=True)
        return {
            'success': False,
            'message': f'Error verifying reCAPTCHA: {str(e)}'
        }

@csrf_exempt
@require_POST
def book_demo(request):
    """
    Process demo booking form submissions and send email notifications
    """
    # Check if it's an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        try:
            # Get form data
            name = request.POST.get('name', '')
            email = request.POST.get('email', '')
            phone = request.POST.get('phone', '')
            company = request.POST.get('company', '')
            
            # Validate required fields
            if not all([name, email, phone]):
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.'
                })
                
            # Prepare email content
            email_subject = f"Demo Request: {name} from {company or 'N/A'}"
            email_message = f"""
            New demo request:
            
            Name: {name}
            Email: {email}
            Phone: {phone}
            Company: {company or 'Not provided'}
            
            Date Requested: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
            
            # Send email using EmailMessage for more control
            from_email = 'noreply@cleaningbizai.com'  # Use a consistent from address
            recipient_list = ['kashifmehmood926@gmail.com', 'ceocleaningacademy@gmail.com']
            
            # Send email notification
            email = EmailMessage(
                subject=email_subject,
                body=email_message,
                from_email=from_email,
                to=recipient_list,
                reply_to=[email],  # Set reply-to as the user's email
            )
            email.send(fail_silently=False)
            
            logger.info(f"Demo request sent successfully from {email}")
            
            return JsonResponse({
                'success': True,
                'message': 'Your demo request has been sent successfully! We will get back to you soon.'
            })
            
        except Exception as e:
            logger.error(f"Error in demo booking form: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'An error occurred: {str(e)}'
            })
    
    # If not an AJAX request, return an error
    return JsonResponse({
        'success': False,
        'message': 'Invalid request'
    })









def PrivacyPolicyPage(request):
    return render(request, 'core/PrivacyPolicy_fixed.html')


def TermsOfServicePage(request):
    return render(request, 'core/TermsOfService.html')

@require_http_methods(["POST"])
@login_required
def bulk_delete_leads(request):
    try:
        data = json.loads(request.body)
        lead_ids = data.get('lead_ids', [])
        
        if not lead_ids:
            return JsonResponse({'success': False, 'error': 'No leads selected'})
        
        # Get leads that belong to the user's business
        leads = Lead.objects.filter(
            leadId__in=lead_ids,
            business__user=request.user
        )
        
        # Delete the leads
        deleted_count = leads.count()
        leads.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} lead(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def sitemap(request):
    """
    Render the sitemap page showing all available routes in the application.
    """
    return render(request, 'core/sitemap.html')


@login_required
def open_jobs(request, cleaner_id=None):
    """
    Display open jobs for a specific cleaner
    """
    # Check if user is logged in as a cleaner
    if hasattr(request.user, 'cleaner_profile'):
        # User is a cleaner, only show their jobs
        from automation.models import OpenJob
        cleaner_profile = request.user.cleaner_profile
        business = cleaner_profile.business
        cleaner = cleaner_profile.cleaner
        
        open_jobs = OpenJob.objects.filter(
            cleaner=cleaner_profile,
            status='pending'
        ).select_related('booking').order_by('booking__cleaningDate', 'booking__startTime')
        
    else:
        # User is a business owner/admin
        business = request.user.business_set.first()
        if not business:
            messages.error(request, 'No business found.')
            return redirect('accounts:register_business')
        
        cleaner = None
        open_jobs = []
        
        if cleaner_id:
            # Get specific cleaner's open jobs
            cleaner = get_object_or_404(Cleaners, id=cleaner_id, business=business)
            
            # Get cleaner profile for open jobs
            from accounts.models import CleanerProfile
            cleaner_profile = CleanerProfile.objects.filter(cleaner=cleaner).first()
            
            if cleaner_profile:
                from automation.models import OpenJob
                open_jobs = OpenJob.objects.filter(
                    cleaner=cleaner_profile,
                    status='pending'
                ).select_related('booking').order_by('booking__cleaningDate', 'booking__startTime')
        else:
            # Get all open jobs for the business
            from automation.models import OpenJob
            from accounts.models import CleanerProfile
            
            cleaner_profiles = CleanerProfile.objects.filter(business=business)
            open_jobs = OpenJob.objects.filter(
                cleaner__in=cleaner_profiles,
                status='pending'
            ).select_related('booking', 'cleaner__cleaner').order_by('booking__cleaningDate', 'booking__startTime')
    
    context = {
        'cleaner': cleaner,
        'open_jobs': open_jobs,
        'title': f'Open Jobs - {cleaner.name if cleaner else "All Cleaners"}',
    }
    
    return render(request, 'automation/open_jobs.html', context)


@login_required
@require_POST
@transaction.atomic
def accept_open_job(request, job_id):
    """
    Accept an open job for a cleaner
    """
    from automation.models import OpenJob
    
    # Get the open job
    job = get_object_or_404(OpenJob, id=job_id)
    
    if job.cleaner.user != request.user:
        messages.error(request, 'You do not have permission to accept this job.')
        return redirect('cleaner_open_jobs', cleaner_id=job.cleaner.cleaner.id)
    
    # Update the job status
    job.status = 'accepted'
    job.save()
    
    # Assign the booking to the cleaner
    booking = job.booking
    booking.cleaner = job.cleaner.cleaner
    booking.save()

    other_job_objs = OpenJob.objects.filter(booking=booking).exclude(id=job.id)
    print(f"other_job_objs: {other_job_objs.count()}")
    for other_job_obj in other_job_objs:
        other_job_obj.status = 'closed'
        other_job_obj.save()
    
    # Add success message
    messages.success(request, f'Job {job.id} has been accepted successfully!')
    
    # Redirect back to the cleaner detail page
    return redirect('cleaner_detail', cleaner_id=job.cleaner.cleaner.id)


@login_required
@require_POST
@transaction.atomic
def reject_open_job(request, job_id):
    """
    Reject an open job for a cleaner and send the job to other available cleaners if no pending jobs exist
    """
    from automation.models import OpenJob
    from bookings.utils import send_jobs_to_cleaners
    
    print(f"Processing job rejection for job_id: {job_id}")
    
    # Get the open job
    job = get_object_or_404(OpenJob, id=job_id)
    print(f"Found job: {job.id} for booking: {job.booking.bookingId} and cleaner: {job.cleaner.cleaner.id}")
    
    if job.cleaner.user != request.user:
        messages.error(request, 'You do not have permission to reject this job.')
        return redirect('cleaner_open_jobs', cleaner_id=job.cleaner.cleaner.id)
    
    # Update the job status
    job.status = 'rejected'
    job.save()
    print(f"Job {job.id} marked as rejected")

    booking = job.booking
    if booking.business.job_assignment == 'high_rated':
        cleaner_id_to_exclude = job.cleaner.cleaner.id
        print(f"Checking for other pending jobs for booking {booking.bookingId}")

        # Get all pending jobs for this booking (regardless of assignment type)
        other_job_objs = OpenJob.objects.filter(booking=booking, status='pending').exclude(id=job.id)
        print(f"other_job_objs: {other_job_objs.count()}")
        
        # If no other pending jobs exist, send this job to all other available cleaners
        if other_job_objs.count() == 0:
            print("Sending jobs to cleaners")
            print(f"exclude_ids: {cleaner_id_to_exclude}")
            print(f"No pending jobs found, sending to other cleaners excluding cleaner {cleaner_id_to_exclude}")
            
            # Get all previously rejected cleaners for this booking to exclude them too
            rejected_cleaner_ids = list(OpenJob.objects.filter(
                booking=booking, 
                status='rejected'
            ).values_list('cleaner__cleaner__id', flat=True))
            
            # Make sure the current cleaner is in the exclude list
            if cleaner_id_to_exclude not in rejected_cleaner_ids:
                rejected_cleaner_ids.append(cleaner_id_to_exclude)
                
            print(f"Excluding these cleaner IDs: {rejected_cleaner_ids}")
            
            # Send jobs to all available cleaners except those who already rejected
            result = send_jobs_to_cleaners(booking.business, booking, exclude_ids=rejected_cleaner_ids, assignment_check_null=True)
            print(f"send_jobs_to_cleaners result: {result}")
        else:
            print("Other pending jobs exist, not sending to more cleaners")
    
    # Add success message
    messages.success(request, f'Job {job.id} has been rejected successfully!')
    return redirect('cleaner_open_jobs', cleaner_id=job.cleaner.cleaner.id)



def confirm_arrival(request, booking_id):
    print(request.user)
    booking = Booking.objects.get(bookingId=booking_id)
    
    from .emails import send_arrival_confirmation_email
    # Send Email to Client
    send_arrival_confirmation_email(booking)
    
    # Update Booking Status
    booking.arrival_confirmed_at = timezone.now()
    booking.save()
    
    # Add success message
    messages.success(request, 'Arrival confirmed successfully!')
    
    # Redirect back to the cleaner detail page
    return redirect('cleaner_detail', cleaner_id=booking.cleaner.id)


def confirm_completed(request, booking_id):
    booking = Booking.objects.get(bookingId=booking_id)
    
    # Update Booking Status
    booking.completed_at = timezone.now()
    booking.isCompleted = True
    booking.save()
    
    # Add booking to existing pending payout or create a new one
    try:
        from accounts.models import CleanerProfile
        from bookings.payout_models import CleanerPayout
        import uuid
        
        # Get the cleaner profile
        cleaner_profile = CleanerProfile.objects.get(cleaner=booking.cleaner)
        
        # Calculate payout amount
        amount = booking.get_cleaner_payout()
        
        # Check if there's an existing pending payout for this cleaner
        existing_payout = CleanerPayout.objects.filter(
            business=booking.business,
            cleaner_profile=cleaner_profile,
            status='pending'
        ).first()
        
        if existing_payout:
            # Add this booking to the existing payout
            existing_payout.bookings.add(booking)
            
            # Update the payout amount
            existing_payout.amount += amount
            existing_payout.save()
            
            # Add success message about adding to existing payout
            messages.success(request, f"Booking marked as completed and added to existing payout #{existing_payout.payout_id}. New payout total: ${existing_payout.amount:.2f}")
        else:
            # Create a new payout
            payout = CleanerPayout.objects.create(
                business=booking.business,
                cleaner_profile=cleaner_profile,
                amount=amount,
                status='pending',
                notes=f"Automatically created when booking {booking.bookingId} was completed"
            )
            
            # Add this booking to the payout
            payout.bookings.add(booking)
            
            # Add success message about new payout
            messages.success(request, f"Booking marked as completed and new payout of ${amount:.2f} has been created.")
    except Exception as e:
        logger.error(f"Error creating automatic payout: {str(e)}")
        messages.success(request, 'Booking marked as completed successfully!')
        messages.warning(request, 'There was an issue creating the automatic payout. Please contact your administrator.')
    
    # Send completion notification emails to cleaner, client, and business owner
    from .emails import send_completion_notification_emails
    send_completion_notification_emails(booking)
    
    # Redirect back to the cleaner detail page
    return redirect('cleaner_detail', cleaner_id=booking.cleaner.id)



def update_cleaner_login(request, cleaner_id):
    cleaner = get_object_or_404(Cleaners, id=cleaner_id)
    cleaner_profile = CleanerProfile.objects.get(cleaner=cleaner)
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            print(f"Username: {username}")
            cleaner_profile.user.username = username
            # Update password if provided
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            if password1 and password2 and password1 == password2:
                cleaner_profile.user.set_password(password1)
            
            cleaner_profile.user.save()
            cleaner_profile.save()
            messages.success(request, 'Login details updated successfully.')
            return redirect('cleaner_detail', cleaner_id=cleaner.id)
        except Exception as e:
            messages.error(request, f'Error updating login details: {str(e)}')
    
    messages.error(request, 'Invalid request method.')
    return redirect('cleaner_detail', cleaner_id=cleaner.id)

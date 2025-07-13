from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q, Sum, Count
import csv
import datetime
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from datetime import timedelta
from accounts.models import ApiCredential, Business, User, BusinessSettings
from subscription.models import SubscriptionPlan, BusinessSubscription, Coupon, Feature, BillingHistory
from saas.models import PlatformSettings, SupportTicket, TicketComment
from bookings.models import Booking
from invoice.models import Invoice
from automation.models import Lead

# Helper function to check if user is admin
def is_admin(user):
    return user.is_staff or user.is_superuser

# Dashboard index view
@login_required
@user_passes_test(is_admin)
def dashboard_index(request):   
    # Get counts for dashboard stats
    total_businesses = Business.objects.count()
    active_subscriptions = BusinessSubscription.objects.filter(status='active').count()
    pending_approvals = Business.objects.filter(isApproved=False).count()
    
    # Calculate monthly revenue
    monthly_revenue = BusinessSubscription.objects.filter(
        status__in=['active', 'cancelled', 'past_due']
    ).aggregate(
        total=Sum('plan__price')
    )['total'] or 0
    
    # Get recent businesses
    recent_businesses = Business.objects.all().order_by('-createdAt')[:5]
    
    # Get recent subscriptions
    recent_subscriptions = BusinessSubscription.objects.all().order_by('-start_date')[:5]
    
    # Get recent activities
    from admin_dashbaord.models import ActivityLog
    recent_activities = ActivityLog.objects.all().order_by('-timestamp')[:10]
    
    context = {
        'total_businesses': total_businesses,
        'active_subscriptions': active_subscriptions,
        'pending_approvals': pending_approvals,
        'monthly_revenue': monthly_revenue,
        'recent_businesses': recent_businesses,
        'recent_subscriptions': recent_subscriptions,
        'recent_activities': recent_activities,
        'today': timezone.now(),
    }
    
    return render(request, 'admin_dashboard/index.html', context)

# Subscription Plans Views
@login_required
@user_passes_test(is_admin)
def subscription_plans(request):
    # Get all subscription plans
    plans_list = SubscriptionPlan.objects.all().order_by('-created_at')
    
    # Pagination
    paginator = Paginator(plans_list, 10)  # Show 10 plans per page
    page_number = request.GET.get('page')
    plans = paginator.get_page(page_number)
    
    context = {
        'plans': plans,
        'active_tab': 'subscription_plans'
    }
    return render(request, 'admin_dashboard/subscription_plans.html', context)

@login_required
@user_passes_test(is_admin)
def add_plan(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        display_name = request.POST.get('display_name')
        price = request.POST.get('price')
        billing_cycle = request.POST.get('billing_cycle')
        plan_tier = request.POST.get('plan_tier')
        plan_type = request.POST.get('plan_type')
        sort_order = request.POST.get('sort_order')
        voice_minutes = request.POST.get('voice_minutes')
        sms_messages = request.POST.get('sms_messages')
        agents = request.POST.get('agents')
        leads = request.POST.get('leads')
        cleaners = request.POST.get('cleaners')
        is_active = 'is_active' in request.POST
        is_invite_only = 'is_invite_only' in request.POST
        
        # Create plan
        plan = SubscriptionPlan.objects.create(
            name=name,
            display_name=display_name,
            price=price,
            billing_cycle=billing_cycle,
            plan_tier=plan_tier,
            plan_type=plan_type,
            sort_order=sort_order,
            voice_minutes=voice_minutes,
            sms_messages=sms_messages,
            agents=agents,
            leads=leads,
            cleaners=cleaners,
            is_active=is_active,
            is_invite_only=is_invite_only
        )
        
        # Add selected features
        feature_ids = request.POST.getlist('features')
        for feature_id in feature_ids:
            try:
                feature = Feature.objects.get(id=feature_id)
                plan.features.add(feature)
            except Feature.DoesNotExist:
                continue
        
        # Check if there's a corresponding plan with the same name but different billing cycle
        # If found, synchronize features
        other_billing_cycle = 'yearly' if billing_cycle == 'monthly' else 'monthly'
        try:
            corresponding_plan = SubscriptionPlan.objects.get(
                plan_tier=plan_tier,
                billing_cycle=other_billing_cycle
            )
            
            # Synchronize features
            corresponding_plan.features.clear()
            for feature in plan.features.all():
                corresponding_plan.features.add(feature)
            
            messages.success(
                request, 
                f'Features have been synchronized with the {other_billing_cycle.capitalize()} version of "{name}".'
            )
        except SubscriptionPlan.DoesNotExist:
            # No corresponding plan found, no synchronization needed
            pass
        
        messages.success(request, f'Subscription plan "{name}" has been created successfully.')
        return redirect('admin_dashboard:subscription_plans')
    
    # Get all available features
    features = Feature.objects.filter(is_active=True).order_by('display_name')
    
    context = {
        'features': features,
        'active_tab': 'subscription_plans'
    }
    return render(request, 'admin_dashboard/create_subscription_plan.html', context)

@login_required
@user_passes_test(is_admin)
def edit_plan(request):
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        
        plan.name = request.POST.get('name')
        plan.display_name = request.POST.get('display_name')
        plan.price = request.POST.get('price')
        plan.billing_cycle = request.POST.get('billing_cycle')
        plan.plan_tier = request.POST.get('plan_tier')
        plan.plan_type = request.POST.get('plan_type')
        plan.sort_order = request.POST.get('sort_order')
        plan.voice_minutes = request.POST.get('voice_minutes')
        plan.sms_messages = request.POST.get('sms_messages')
        plan.agents = request.POST.get('agents')
        plan.leads = request.POST.get('leads')
        plan.cleaners = request.POST.get('cleaners')
        plan.is_active = 'is_active' in request.POST
        plan.is_invite_only = 'is_invite_only' in request.POST
        
        # Save the plan
        plan.save()
        
        # Update features
        plan.features.clear()  # Remove all existing features
        feature_ids = request.POST.getlist('features')
        for feature_id in feature_ids:
            try:
                feature = Feature.objects.get(id=feature_id)
                plan.features.add(feature)
            except Feature.DoesNotExist:
                continue
        
        # Find corresponding plan with the same name but different billing cycle
        # and synchronize features
        other_billing_cycle = 'yearly' if plan.billing_cycle == 'monthly' else 'monthly'
        try:
            corresponding_plans = SubscriptionPlan.objects.filter(
                plan_tier=plan.plan_tier,
                billing_cycle=other_billing_cycle
            )
            
            # Synchronize features
            for corresponding_plan in corresponding_plans:
                corresponding_plan.features.clear()
                for feature in plan.features.all():
                    corresponding_plan.features.add(feature)
            
            messages.success(
                request, 
                f'Features have been synchronized with the {other_billing_cycle.capitalize()} version of "{plan.name}".'
            )
        except SubscriptionPlan.DoesNotExist:
            # No corresponding plan found, no synchronization needed
            pass
        
        messages.success(request, f'Subscription plan "{plan.name}" has been updated successfully.')
        return redirect('admin_dashboard:subscription_plans')
    
    # Get the plan to edit
    plan_id = request.GET.get('id')
    if not plan_id:
        messages.error(request, 'No plan specified for editing.')
        return redirect('admin_dashboard:subscription_plans')
    
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    features = Feature.objects.filter(is_active=True).order_by('display_name')
    
    context = {
        'plan': plan,
        'features': features,
        'active_tab': 'subscription_plans'
    }
    return render(request, 'admin_dashboard/edit_subscription_plan.html', context)

@login_required
@user_passes_test(is_admin)
def delete_plan(request):
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        
        # Check if plan is being used by any active subscriptions
        active_subscriptions = BusinessSubscription.objects.filter(plan=plan, status='active').exists()
        
        if active_subscriptions:
            messages.error(request, f'Cannot delete plan "{plan.name}" as it is currently being used by active subscriptions.')
        else:
            plan_name = plan.name
            plan.delete()
            messages.success(request, f'Subscription plan "{plan_name}" has been deleted successfully.')
        
        return redirect('admin_dashboard:subscription_plans')
    
    return redirect('admin_dashboard:subscription_plans')

# Feature Management Views
@login_required
@user_passes_test(is_admin)
def features(request):
    # Get all features
    features_list = Feature.objects.all().order_by('display_name')
    
    # Pagination
    paginator = Paginator(features_list, 10)  # Show 10 features per page
    page_number = request.GET.get('page')
    features = paginator.get_page(page_number)
    
    context = {
        'features': features,
        'active_tab': 'features'
    }
    return render(request, 'admin_dashboard/features.html', context)

@login_required
@user_passes_test(is_admin)
def add_feature(request):
    if request.method == 'POST':
        display_name = request.POST.get('display_name')
        name = request.POST.get('name')
        description = request.POST.get('description')
        is_active = 'is_active' in request.POST
        
        # Create feature
        feature = Feature.objects.create(
            display_name=display_name,
            name=name,
            description=description,
            is_active=is_active
        )
        
        messages.success(request, f'Feature "{display_name}" has been created successfully.')
        return redirect('admin_dashboard:features')
    
    return redirect('admin_dashboard:features')

@login_required
@user_passes_test(is_admin)
def edit_feature(request):
    if request.method == 'POST':
        feature_id = request.POST.get('feature_id')
        feature = get_object_or_404(Feature, id=feature_id)
        
        feature.display_name = request.POST.get('display_name')
        feature.name = request.POST.get('name')
        feature.description = request.POST.get('description')
        feature.is_active = 'is_active' in request.POST
        
        feature.save()
        
        messages.success(request, f'Feature "{feature.display_name}" has been updated successfully.')
        return redirect('admin_dashboard:features')
    
    return redirect('admin_dashboard:features')

@login_required
@user_passes_test(is_admin)
def delete_feature(request):
    if request.method == 'POST':
        feature_id = request.POST.get('feature_id')
        feature = get_object_or_404(Feature, id=feature_id)
        
        # Check if feature is being used by any plans
        plans_using_feature = feature.subscription_plans.count()
        
        feature_name = feature.display_name
        feature.delete()
        
        if plans_using_feature > 0:
            messages.success(request, f'Feature "{feature_name}" has been deleted and removed from {plans_using_feature} subscription plan(s).')
        else:
            messages.success(request, f'Feature "{feature_name}" has been deleted successfully.')
        
        return redirect('admin_dashboard:features')
    
    return redirect('admin_dashboard:features')

# Coupon Views
@login_required
@user_passes_test(is_admin)
def coupons(request):
    from subscription.models import Coupon
    
    coupons = Coupon.objects.all().order_by('-created_at')
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    # Pagination
    paginator = Paginator(coupons, 10)
    page_number = request.GET.get('page', 1)
    coupons = paginator.get_page(page_number)
    
    # Add applicable_plans_ids to each coupon for the frontend
    for coupon in coupons:
        coupon.applicable_plans_ids = list(coupon.applicable_plans.values_list('id', flat=True))
        coupon.is_expired = coupon.expiry_date and coupon.expiry_date < timezone.now().date()
    
    context = {
        'coupons': coupons,
        'subscription_plans': subscription_plans,
    }
    
    return render(request, 'admin_dashboard/coupons.html', context)

@login_required
@user_passes_test(is_admin)
def add_coupon(request):
    from subscription.models import Coupon
    
    if request.method == 'POST':
        code = request.POST.get('code').upper()
        discount_type = request.POST.get('discount_type')
        discount_value = request.POST.get('discount_value')
        limit_type = request.POST.get('limit_type', 'overall')
        usage_limit = request.POST.get('usage_limit') or None
        expiry_date = request.POST.get('expiry_date') or None
        is_active = 'is_active' in request.POST
        description = request.POST.get('description', '')

        if Coupon.objects.filter(code=code).exists():
            messages.error(request, 'Coupon code already exists.')
            return redirect('admin_dashboard:coupons')
        
        # Create coupon
        coupon = Coupon.objects.create(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            limit_type=limit_type,
            usage_limit=usage_limit,
            expiry_date=expiry_date,
            is_active=is_active,
            description=description
        )
        
        # Add applicable plans if selected
        applicable_plans = request.POST.getlist('applicable_plans')
        if applicable_plans:
            for plan_id in applicable_plans:
                plan = get_object_or_404(SubscriptionPlan, id=plan_id)
                coupon.applicable_plans.add(plan)
        
        messages.success(request, f'Coupon code "{code}" has been created successfully.')
        return redirect('admin_dashboard:coupons')
    
    # GET request - show the create coupon form
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    context = {
        'subscription_plans': subscription_plans,
    }
    return render(request, 'admin_dashboard/create_coupon.html', context)

@login_required
@user_passes_test(is_admin)
def edit_coupon(request):
    from subscription.models import Coupon
    
    if request.method == 'POST':
        coupon_id = request.POST.get('coupon_id')
        coupon = get_object_or_404(Coupon, id=coupon_id)
        
        coupon.code = request.POST.get('code').upper()
        coupon.discount_type = request.POST.get('discount_type')
        coupon.discount_value = request.POST.get('discount_value')
        coupon.limit_type = request.POST.get('limit_type', 'overall')
        coupon.usage_limit = request.POST.get('usage_limit') or None
        coupon.expiry_date = request.POST.get('expiry_date') or None
        coupon.is_active = 'is_active' in request.POST
        coupon.description = request.POST.get('description', '')
        
        # Update applicable plans
        coupon.applicable_plans.clear()
        applicable_plans = request.POST.getlist('applicable_plans')
        if applicable_plans:
            for plan_id in applicable_plans:
                plan = get_object_or_404(SubscriptionPlan, id=plan_id)
                coupon.applicable_plans.add(plan)
        
        coupon.save()
        
        messages.success(request, f'Coupon code "{coupon.code}" has been updated successfully.')
        return redirect('admin_dashboard:coupons')
    
    # GET request - show the edit coupon form
    coupon_id = request.GET.get('id')
    if not coupon_id:
        messages.error(request, "No coupon ID provided.")
        return redirect('admin_dashboard:coupons')
    
    coupon = get_object_or_404(Coupon, id=coupon_id)
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    context = {
        'coupon': coupon,
        'subscription_plans': subscription_plans,
    }
    return render(request, 'admin_dashboard/edit_coupon.html', context)

@login_required
@user_passes_test(is_admin)
def delete_coupon(request):
    if request.method == 'POST':
        from subscription.models import Coupon
        
        coupon_id = request.POST.get('coupon_id')
        coupon = get_object_or_404(Coupon, id=coupon_id)
        
        code = coupon.code
        coupon.delete()
        
        messages.success(request, f'Coupon code "{code}" has been deleted successfully.')
        return redirect('admin_dashboard:coupons')
    
    return redirect('admin_dashboard:coupons')

# Business Management Views
@login_required
@user_passes_test(is_admin)
def businesses(request):
    businesses = Business.objects.filter(user__isnull=False).order_by('-createdAt')

    # Pagination
    paginator = Paginator(businesses, 50)
    page_number = request.GET.get('page', 1)
    businesses = paginator.get_page(page_number)
    
    # Get all users for the add business form - Whose Business Profile is not created Yet
    # Exclude users who already have a business profile
    users_with_business = Business.objects.exclude(user__isnull=True).values_list('user_id', flat=True)
    users = User.objects.exclude(id__in=users_with_business).order_by('username')
    
    context = {
        'businesses': businesses,
        'users': users,
    }
    
    return render(request, 'admin_dashboard/businesses.html', context)
   

@login_required
@user_passes_test(is_admin)
def business_detail(request, business_id):
    business = get_object_or_404(Business, id=business_id)
    
    # Get active subscription
    try:
        business.active_subscription = business.active_subscription()
    except BusinessSubscription.DoesNotExist:
        business.active_subscription = None
    
    # Get all active subscriptions (including trial plans)
    business.all_subscriptions = BusinessSubscription.objects.filter(
        business=business,
        is_active=True
    ).exclude(status='ended').order_by('-start_date')
    
    # Get previous subscriptions (ended or cancelled)
    business.previous_subscriptions = BusinessSubscription.objects.filter(
        business=business,
        status__in=['ended', 'cancelled'],
    ).order_by('-end_date')
    
    # Get future subscription plan if one is scheduled
    business.future_subscription = None
    
    
    if business.active_subscription and business.active_subscription.next_plan_id:
        try:
            business.future_subscription = {
                'current_subscription': business.active_subscription,
                'next_plan': SubscriptionPlan.objects.get(id=business.active_subscription.next_plan_id),
                'effective_date': business.active_subscription.next_billing_date
            }
        except SubscriptionPlan.DoesNotExist:
            pass

    # Get business statistics
    # Bookings stats - matching the categories in bookings.html
    business.bookings_stats = {
        'total': Booking.objects.filter(business=business).count(),
        'upcoming': Booking.objects.filter(business=business, cleaningDate__gte=timezone.now().date()).exclude(paymentMethod=None).count(),
        'awaiting_payment': Booking.objects.filter(business=business, paymentMethod=None).count(),
        'past': Booking.objects.filter(business=business, cleaningDate__lt=timezone.now().date()).count(),
        'cancelled': Booking.objects.filter(business=business, cancelled_at__isnull=False).count(),
        'revenue': Booking.objects.filter(business=business).aggregate(total=Sum('totalPrice'))['total'] or 0
    }
    
    # Leads stats
    business.leads_stats = {
        'total': Lead.objects.filter(business=business).count(),
       
    }
    
    
    
    # Invoices stats - matching the categories in invoices.html
    invoices = Invoice.objects.filter(booking__business=business)
    
    # Get payment statuses
    payment_statuses = {}
    for invoice in invoices:
        try:
            status = invoice.payment_details.status
            if status in payment_statuses:
                payment_statuses[status] += 1
            else:
                payment_statuses[status] = 1
        except:
            pass
    
    business.invoices_stats = {
        'total': invoices.count(),
        'paid': invoices.filter(isPaid=True).count(),
        'pending': invoices.filter(isPaid=False).count(),
        'authorized': payment_statuses.get('AUTHORIZED', 0),
        'total_amount': invoices.aggregate(total=Sum('amount'))['total'] or 0,
        'paid_amount': invoices.filter(isPaid=True).aggregate(total=Sum('amount'))['total'] or 0
    }

    # Get subscription plans for the add subscription form
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    # Get API credentials
    try:
        api_credentials = business.apicredential
    except:
        api_credentials = None
    # Get business pricing settings
    try:
        business_settings = business.settings
    except:
        business_settings = None
    
    context = {
        'business': business,
        'subscription_plans': subscription_plans,
        'api_credentials': api_credentials,
        'business_settings': business_settings,
        'today': timezone.now(),
    }
    
    return render(request, 'admin_dashboard/business_detail.html', context)

@login_required
@user_passes_test(is_admin)
def add_business(request):
    if request.method == 'POST':
        business_name = request.POST.get('businessName')
        user_id = request.POST.get('user')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        is_approved = 'isApproved' in request.POST
        is_active = 'isActive' in request.POST
        use_call = 'useCall' in request.POST
        time_to_wait = request.POST.get('timeToWait', 0)
        
        # Clean and validate phone number
        if phone:
            # Remove all non-digit characters
            phone_digits = ''.join(filter(str.isdigit, phone))
            
            # Validate phone number length
            if len(phone_digits) == 10:
                # Format as +1XXXXXXXXXX for storage
                phone = '+1' + phone_digits
            elif len(phone_digits) != 0:
                messages.error(request, 'Please enter a valid 10-digit phone number.')
                return redirect('admin_dashboard:businesses')
        
        # Get the user or return error if not found
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            messages.error(request, 'User not found. Please select a valid user.')
            return redirect('admin_dashboard:businesses')
        
        # Create business with the correct fields from the Business model
        business = Business.objects.create(
            user=user,
            businessName=business_name,
            phone=phone,
            address=address,
            isApproved=is_approved,
            isActive=is_active,
            useCall=use_call,
            timeToWait=int(time_to_wait) if time_to_wait else 10
        )

        
        messages.success(request, f'Business "{business_name}" has been created successfully.')
        return redirect('admin_dashboard:businesses')
    
    # Get all users for the form
    users = User.objects.all()
    context = {
        'users': users
    }
    return render(request, 'admin_dashboard/add_business.html', context)

@login_required
@user_passes_test(is_admin)
def edit_business(request):
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        
        # Store previous approval status to check if it changed
        was_approved_before = business.isApproved
        
        # Update business fields
        business.businessName = request.POST.get('businessName')
        
        # Clean and validate phone number
        phone = request.POST.get('phone')
        if phone:
            # Remove all non-digit characters
            phone_digits = ''.join(filter(str.isdigit, phone))
            
            # Validate phone number length
            if len(phone_digits) == 10:
                # Format as +1XXXXXXXXXX for storage
                business.phone = '+1' + phone_digits
            elif len(phone_digits) != 0:
                messages.error(request, 'Please enter a valid 10-digit phone number.')
                return redirect('admin_dashboard:businesses')
        else:
            business.phone = phone
            
        business.address = request.POST.get('address')
        business.isApproved = 'isApproved' in request.POST
        business.isActive = 'isActive' in request.POST
        business.useCall = 'useCall' in request.POST
        business.timeToWait = int(request.POST.get('timeToWait', 0))
        
        business.save()
        
     
        
        messages.success(request, f'Business "{business.businessName}" has been updated successfully.')
        
        # Redirect back to the detail page if that's where we came from
        if 'business_detail' in request.META.get('HTTP_REFERER', ''):
            return redirect('admin_dashboard:business_detail', business_id=business.id)
        
        return redirect('admin_dashboard:businesses')
    
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def approve_business(request):
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        
        # Update approval status
        business.isApproved = True
        business.isActive = True
        business.save()

        # Create ApiConfig and BusinessSettings
        ApiCredential.objects.get_or_create(business=business)
        BusinessSettings.objects.get_or_create(business=business)

        # Send email notification to business owner
        try:
            subject = 'Your Business Has Been Approved!'
            message = f"""Hello {business.user.username},

            Congratulations! Your business '{business.businessName}' has been approved by our team.

            You now have full access to all features of CleaningBiz AI. Log in to your account to get started.

            Thank you for choosing CleaningBiz AI!

            Best regards,
            The CleaningBiz AI Team
            """
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [business.user.email]
            send_mail(subject, message, from_email, recipient_list)
        except Exception as e:
            # Log the error but don't stop the approval process
            print(f"Error sending approval email: {str(e)}")
        
        
        messages.success(request, f'Business "{business.businessName}" has been approved successfully.')
        
        # Redirect back to the detail page if that's where we came from
        if 'business_detail' in request.META.get('HTTP_REFERER', ''):
            return redirect('admin_dashboard:business_detail', business_id=business.id)
        
        return redirect('admin_dashboard:businesses')
    
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def reject_business(request):
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        
        # Update approval status
        business.isRejected = True
        business.save()

        # Send email notification to business owner
        try:
            subject = 'Your Business Has Been Rejected'
            message = f"""Hello {business.user.username},

            Your business '{business.businessName}' has been rejected by our team.

            Thank you for choosing CleaningBiz AI!

            Best regards,
            The CleaningBiz AI Team
            """
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [business.user.email]
            send_mail(subject, message, from_email, recipient_list)
        except Exception as e:
            # Log the error but don't stop the rejection process
            print(f"Error sending rejection email: {str(e)}")
        
        messages.success(request, f'Business "{business.businessName}" has been rejected.')
        
        # Redirect back to the detail page if that's where we came from
        if 'business_detail' in request.META.get('HTTP_REFERER', ''):
            return redirect('admin_dashboard:business_detail', business_id=business.id)
        
        return redirect('admin_dashboard:businesses')
    
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def delete_business(request):
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        
        business_name = business.businessName
        business.delete()
        
        messages.success(request, f'Business "{business_name}" has been deleted successfully.')
        return redirect('admin_dashboard:businesses')
    
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def edit_api_credentials(request):
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        
        # Get or create API credentials for the business
        api_credentials, created = ApiCredential.objects.get_or_create(business=business)
        

        api_credentials.twilioSmsNumber = request.POST.get('twilioSmsNumber', api_credentials.twilioSmsNumber)
        api_credentials.twilioAccountSid = request.POST.get('twilioAccountSid', api_credentials.twilioAccountSid)
        api_credentials.twilioAuthToken = request.POST.get('twilioAuthToken', api_credentials.twilioAuthToken)
        
        # Save the updated credentials
        api_credentials.save()
        
        messages.success(request, f'API credentials for {business.businessName} have been updated successfully.')
        return redirect('admin_dashboard:business_detail', business_id=business.id)
    
    return redirect('admin_dashboard:business_detail', business_id=business.id)

@login_required
@user_passes_test(is_admin)
def export_businesses(request):
    businesses = Business.objects.all().order_by('-createdAt')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="businesses.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Business ID', 'Business Name', 'Owner', 'Email', 'Phone', 
                    'Address', 'City', 'State', 'ZIP', 'Status', 'Created Date'])
    
    for business in businesses:
        writer.writerow([
            business.businessId,
            business.businessName,
            business.user.get_full_name() if business.user else 'N/A',
            business.email,
            business.phone,
            business.address,
            business.city,
            business.state,
            business.zipCode,
            'Approved' if business.isApproved else 'Pending',
            business.createdAt.strftime('%Y-%m-%d')
        ])
    
    return response

# Subscription Management Views
@login_required
@user_passes_test(is_admin)
def subscriptions(request):
    """View to display all business subscriptions"""
    from subscription.models import BusinessSubscription, SubscriptionPlan
    
    all_subscriptions = BusinessSubscription.objects.all().order_by('-start_date')
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    # Pagination
    paginator = Paginator(all_subscriptions, 10)
    page_number = request.GET.get('page', 1)
    subscriptions = paginator.get_page(page_number)
    
    context = {
        'subscriptions': subscriptions,
        'subscription_plans': subscription_plans,
        'today': timezone.now(),
    }
    
    return render(request, 'admin_dashboard/subscriptions.html', context)

@login_required
@user_passes_test(is_admin)
def subscription_detail(request, subscription_id):
    """View to display detailed information about a specific subscription"""
    from subscription.models import BusinessSubscription, BillingHistory, UsageTracker
    from usage_analytics.services.usage_service import UsageService

    
    # Get the subscription
    subscription = get_object_or_404(BusinessSubscription, id=subscription_id)
    business = subscription.business
    
    # Get subscription features
    features = subscription.plan.features.filter(is_active=True)
    feature_list = [feature.name for feature in features]
    
    # Get billing history
    billing_history = BillingHistory.objects.filter(subscription=subscription).order_by('-billing_date')

    subscription_data = {
        'id': subscription.id,
        'name': subscription.plan.name,
        'price': subscription.plan.price,
        'status': subscription.status,
        'next_billing_date': subscription.next_billing_date or subscription.end_date,
        'start_date': subscription.start_date,
        'end_date': subscription.end_date,
        'voice_minutes_limit': subscription.plan.voice_minutes,
        'sms_messages_limit': subscription.plan.sms_messages,
        'agents_limit': subscription.plan.agents,
        'leads_limit': subscription.plan.leads,
        'cleaners_limit': subscription.plan.cleaners,
        'features': feature_list,
        'billing_cycle': subscription.plan.billing_cycle,
        'plan_tier': subscription.plan.plan_tier,
        'plan_type': subscription.plan.plan_type,
        'trial_end_date': subscription.end_date
    }
    
    usage_service = UsageService()
    usage_data = usage_service.get_business_usage(business, start_date=subscription.start_date, end_date=subscription.end_date)


    
    
    
    context = {
        'subscription': subscription_data,
        'business': business,
        'billing_history': billing_history,
        'usage': usage_data,
      
    }
    
    return render(request, 'admin_dashboard/subscription_detail.html', context)

# User Management Views
@login_required
@user_passes_test(is_admin)
def users(request):
    """View to display all users with filtering and pagination"""
    from django.contrib.auth.models import User, Group
    
    # Get all users except the current user
    users = User.objects.exclude(id=request.user.id).order_by('-date_joined')
    
    # Filter by user type (staff, superuser, regular)
    user_type = request.GET.get('user_type', 'all')
    if user_type == 'staff':
        users = users.filter(is_staff=True, is_superuser=False)
    elif user_type == 'superuser':
        users = users.filter(is_superuser=True)
    elif user_type == 'regular':
        users = users.filter(is_staff=False, is_superuser=False)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)
    
    # Get all groups for user type selection
    groups = Group.objects.all()
    
    context = {
        'users': users,
        'groups': groups,
        'user_type': user_type,
        'search_query': search_query,
    }
    
    return render(request, 'admin_dashboard/users.html', context)

@login_required
@user_passes_test(is_admin)
def add_user(request):
    """View to add a new user"""
    from django.contrib.auth.models import User, Group
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        password = request.POST.get('password')
        is_staff = 'is_staff' in request.POST
        is_superuser = 'is_superuser' in request.POST
        groups = request.POST.getlist('groups')
        
        # Validate username uniqueness
        if User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already exists.')
            return redirect('admin_dashboard:add_user')
        
        # Validate email uniqueness
        if email and User.objects.filter(email=email).exists():
            messages.error(request, f'Email "{email}" is already in use.')
            return redirect('admin_dashboard:add_user')
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        
        # Add user to selected groups
        for group_id in groups:
            group = get_object_or_404(Group, id=group_id)
            user.groups.add(group)
        
        messages.success(request, f'User "{username}" has been created successfully.')
        return redirect('admin_dashboard:users')
    
    # Get all groups for user type selection
    groups = Group.objects.all()
    
    context = {
        'groups': groups,
    }
    
    return render(request, 'admin_dashboard/create_user.html', context)

@login_required
@user_passes_test(is_admin)
def edit_user(request):
    """View to edit an existing user"""
    from django.contrib.auth.models import User, Group
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        user = get_object_or_404(User, id=user_id)
        
        # Don't allow editing the current user through this interface
        if user.id == request.user.id:
            messages.error(request, "You cannot edit your own account through this interface.")
            return redirect('admin_dashboard:users')
        
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        is_active = 'is_active' in request.POST
        is_staff = 'is_staff' in request.POST
        is_superuser = 'is_superuser' in request.POST
        groups = request.POST.getlist('groups')
        new_password = request.POST.get('new_password')
        
        # Validate username uniqueness
        if username != user.username and User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already exists.')
            return redirect('admin_dashboard:edit_user')
        
        # Validate email uniqueness
        if email and email != user.email and User.objects.filter(email=email).exists():
            messages.error(request, f'Email "{email}" is already in use.')
            return redirect('admin_dashboard:edit_user')
        
        # Update user
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = is_active
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        
        # Update password if provided
        if new_password:
            user.set_password(new_password)
        
        user.save()
        
        # Update groups
        user.groups.clear()
        for group_id in groups:
            group = get_object_or_404(Group, id=group_id)
            user.groups.add(group)
        
        messages.success(request, f'User "{username}" has been updated successfully.')
        return redirect('admin_dashboard:users')
    
    # GET request - show the edit user form
    user_id = request.GET.get('id')
    if not user_id:
        messages.error(request, "No user ID provided.")
        return redirect('admin_dashboard:users')
    
    user = get_object_or_404(User, id=user_id)
    
    # Don't allow editing the current user through this interface
    if user.id == request.user.id:
        messages.error(request, "You cannot edit your own account through this interface.")
        return redirect('admin_dashboard:users')
    
    # Get all groups for user type selection
    groups = Group.objects.all()
    
    context = {
        'user_obj': user,  # Using user_obj to avoid conflict with request.user
        'groups': groups,
        'user_groups': [group.id for group in user.groups.all()],
    }
    
    return render(request, 'admin_dashboard/edit_user.html', context)

@login_required
@user_passes_test(is_admin)
def delete_user(request):
    """View to delete a user"""
    from django.contrib.auth.models import User
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        user = get_object_or_404(User, id=user_id)
        
        # Don't allow deleting the current user
        if user.id == request.user.id:
            messages.error(request, "You cannot delete your own account.")
            return redirect('admin_dashboard:users')
        
        username = user.username
        user.delete()
        
        messages.success(request, f'User "{username}" has been deleted successfully.')
    
    return redirect('admin_dashboard:users')

# Activity Log Views
@login_required
@user_passes_test(is_admin)
def activity_logs(request):
    """View to display activity logs with filtering"""
    from .models import ActivityLog
    
    # Get all activity logs
    logs = ActivityLog.objects.all()
    
    # Filter by activity type
    activity_type = request.GET.get('activity_type', '')
    if activity_type:
        logs = logs.filter(activity_type=activity_type)
    
    # Filter by user
    user_id = request.GET.get('user_id', '')
    if user_id:
        logs = logs.filter(user_id=user_id)
    
    # Filter by date range
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    if start_date:
        logs = logs.filter(timestamp__gte=start_date)
    if end_date:
        logs = logs.filter(timestamp__lte=end_date + ' 23:59:59')
    
    # Search by description
    search_query = request.GET.get('search', '')
    if search_query:
        logs = logs.filter(description__icontains=search_query)
    
    # Get all users for the filter dropdown
    users = User.objects.all()
    
    # Get all activity types for the filter dropdown
    activity_types = dict(ActivityLog.ACTIVITY_TYPES)
    
    # Pagination
    paginator = Paginator(logs, 20)  # Show 20 logs per page
    page_number = request.GET.get('page', 1)
    logs = paginator.get_page(page_number)
    
    context = {
        'logs': logs,
        'users': users,
        'activity_types': activity_types,
        'selected_activity_type': activity_type,
        'selected_user_id': user_id,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
    }
    
    return render(request, 'admin_dashboard/activity_logs.html', context)

@login_required
@user_passes_test(is_admin)
def activity_log_detail(request, log_id):
    """View to display details of a specific activity log"""
    from .models import ActivityLog
    
    log = get_object_or_404(ActivityLog, id=log_id)
    
    context = {
        'log': log,
    }
    
    return render(request, 'admin_dashboard/activity_log_detail.html', context)

@login_required
@user_passes_test(is_admin)
def assign_subscription(request):
    """Assign a subscription plan to a business without requiring payment (admin only)."""
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        plan_id = request.POST.get('subscription_plan')
        
        business = get_object_or_404(Business, id=business_id)
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        
        # Check if business already has an active subscription
       
        current_subscription = business.active_subscription()

        if current_subscription:
            messages.info(request, f'Business {business.businessName} already has an active subscription.')
            return redirect('admin_dashboard:businesses')


        # Create new subscription
        start_date = timezone.now()
        
        # Set end date based on billing cycle
        if plan.billing_cycle == 'monthly':
            end_date = start_date + timezone.timedelta(days=30)
        else:  # yearly
            end_date = start_date + timezone.timedelta(days=365)
        
        # Create the subscription
        subscription = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status='active',
            start_date=start_date,
            end_date=end_date,
            next_billing_date=end_date,
            is_active=True
        )
        
        # Create a billing record for this assignment
        BillingHistory.objects.create(
            business=business,
            subscription=subscription,
            amount=plan.price,
            status='paid',
            billing_date=timezone.now(),
            details={
                'payment_method': 'admin_assignment',
                'payment_date': timezone.now().isoformat(),
                'payment_status': 'COMPLETED',
                'assigned_by_admin': True
            }
        )
        
        messages.success(
            request, 
            f'Subscription plan "{plan.name}" has been assigned to {business.businessName} successfully.'
        )
        
        return redirect('admin_dashboard:business_detail', business_id=business.id)
    
    # If not POST, redirect to businesses list
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def admin_cancel_plan(request):
    """Immediately cancel a subscription plan for a business (admin only)."""

    redirect_url = request.META.get('HTTP_REFERER', 'admin_dashboard:businesses')
    
    if request.method == 'POST':
        subscription_id = request.POST.get('subscription_id')
        if not subscription_id:
            messages.error(request, 'No subscription specified for cancellation.')
            return redirect(redirect_url)
        
        subscription = get_object_or_404(BusinessSubscription, id=subscription_id)
        business = subscription.business
        
        # Immediately terminate the subscription
        subscription.status = 'ended'
        subscription.is_active = False
        subscription.end_date = timezone.now()
        subscription.save()
        
        messages.success(request, f'Subscription for "{business.businessName}" has been terminated immediately.')
        return redirect(redirect_url)
    
    return redirect('admin_dashboard:businesses')

@login_required
@user_passes_test(is_admin)
def admin_change_plan(request):
    """Immediately change a business's subscription plan (admin only)."""
    redirect_url = request.META.get('HTTP_REFERER', 'admin_dashboard:businesses')
    
    if request.method == 'POST':
        subscription_id = request.POST.get('subscription_id')
        new_plan_id = request.POST.get('new_plan_id')

        if not subscription_id or not new_plan_id:
            messages.error(request, 'No subscription or new plan specified for change.')
            return redirect(redirect_url)
        
        # Get the current subscription and new plan
        subscription = get_object_or_404(BusinessSubscription, id=subscription_id)
        new_plan = get_object_or_404(SubscriptionPlan, id=new_plan_id)
        business = subscription.business

        subscriptions = BusinessSubscription.objects.filter(business=business, is_active=True)
        
        with transaction.atomic():
            for subcription in subscriptions:
                # End the current subscription
                subcription.status = 'ended'
                subcription.is_active = False
                subcription.end_date = timezone.now()
                subcription.save()
            
            # Create a new subscription with the new plan
            end_date = timezone.now() + timedelta(days=30 if new_plan.billing_cycle == 'monthly' else 365)
            
            new_subscription = BusinessSubscription.objects.create(
                business=business,
                plan=new_plan,
                status='active',
                start_date=timezone.now(),
                end_date=end_date,
                next_billing_date=end_date,
                is_active=True
            )
            
            # Create a billing record for this change
            BillingHistory.objects.create(
                business=business,
                subscription=new_subscription,
                amount=new_plan.price,
                status='paid',
                billing_date=timezone.now(),
                details={
                    'payment_method': 'admin_change',
                    'payment_date': timezone.now().isoformat(),
                    'payment_status': 'COMPLETED',
                    'changed_from_plan': subscription.plan.name,
                    'changed_by_admin': True
                }
            )
        
        messages.success(request, f'Subscription for "{business.businessName}" has been changed from {subscription.plan.name} to {new_plan.name}.')
        return redirect(redirect_url)
    
    return redirect(redirect_url)

@login_required
@user_passes_test(is_admin)
def analytics(request):
    """View for analytics dashboard page"""
    context = {
        'active_tab': 'analytics'
    }
    return render(request, 'admin_dashboard/analytics.html', context)


@login_required
@user_passes_test(is_admin)
def api_analytics(request):
    """API endpoint to provide analytics data with date range filtering"""
    from django.db.models import Count, Sum, F, Q, ExpressionWrapper, FloatField, IntegerField
    from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
    from django.utils import timezone
    from datetime import datetime, timedelta
    from usage_analytics.services.retell_api_service import RetellAPIService
    from retell_agent.models import RetellAgent
    from ai_agent.models import Chat
    from bookings.models import Booking
    import json
    
    # Get date range from request parameters
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            # Default to last 30 days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=29)
    except (ValueError, TypeError):
        # Handle invalid date format
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Query bookings within date range
    bookings_in_range = Booking.objects.filter(
        cleaningDate__gte=start_date,
        cleaningDate__lte=end_date
    )
    
    # Count total bookings
    total_bookings = bookings_in_range.count()
    
    # Calculate total revenue
    total_revenue = bookings_in_range.aggregate(
        total=Sum('totalPrice')
    )['total'] or 0

  
    try:
        retell_calls = RetellAPIService.list_calls(start_date=start_date, end_date=end_date)
        total_retell_calls = len(retell_calls)
       
    except Exception as e:
        print(f"Error fetching Retell calls: {e}")
        total_retell_calls = 0
    
    # Convert date objects to datetime for Chat filtering
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    try:
        total_chats = Chat.objects.filter(createdAt__gte=start_datetime, createdAt__lte=end_datetime).count()
    except Exception as e:
        print(f"Error fetching chat count: {e}")
        total_chats = 0
    
    # Calculate conversion rate (completed/total)
    completed_bookings = bookings_in_range.filter(isCompleted=True).count()
    
    conversion_rate = round((total_bookings / (total_chats + total_retell_calls)) * 100)
  
    
    # Get distribution data for pie chart (by service type)
    service_type_counts = bookings_in_range.values(
        'serviceType'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    distribution_labels = []
    distribution_values = []

    from bookings.models import serviceTypes
    
    for service in service_type_counts:
        service_name = dict(serviceTypes).get(service['serviceType'], 'Unknown')
        distribution_labels.append(service_name)
        distribution_values.append(service['count'])
    
    # Get time series data
    # Determine appropriate grouping based on date range
    range_days = (end_date - start_date).days + 1
    
    if range_days <= 31:
        # Group by day for ranges up to a month
        time_bookings = bookings_in_range.annotate(
            date=TruncDay('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %d'  # Aug 15
    elif range_days <= 90:
        # Group by week for ranges up to 3 months
        time_bookings = bookings_in_range.annotate(
            date=TruncWeek('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %d'  # Aug 15
    else:
        # Group by month for longer ranges
        time_bookings = bookings_in_range.annotate(
            date=TruncMonth('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %Y'  # Aug 2023
    
    time_series_labels = []
    time_series_values = []
    
    for entry in time_bookings:
        if entry['date']:
            time_series_labels.append(entry['date'].strftime(date_format))
            time_series_values.append(entry['count'])
    
    # Compile response data
    response_data = {
        'total_bookings': total_bookings,
        'total_revenue': float(total_revenue),
        'total_chats': total_chats,
        'total_calls': total_retell_calls,
        'conversion_rate': conversion_rate,
        'distribution_data': {
            'labels': distribution_labels,
            'values': distribution_values
        },
        'time_series_data': {
            'labels': time_series_labels,
            'values': time_series_values
        }
    }
    
    return JsonResponse(response_data)

# Add the business_analytics view function
@login_required
@user_passes_test(is_admin)
def business_analytics(request, business_id):
    """View for displaying analytics for a specific business"""
    business = get_object_or_404(Business, id=business_id)
    
    context = {
        'business': business,
        'active_tab': 'businesses'
    }
    
    return render(request, 'admin_dashboard/business_analytics.html', context)

# Add the business_analytics_api endpoint
@login_required
@user_passes_test(is_admin)
def business_analytics_api(request, business_id):
    """API endpoint to provide analytics data for a specific business with date range filtering"""
    from django.db.models import Count, Sum, F, Q, ExpressionWrapper, FloatField, IntegerField
    from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
    from django.utils import timezone
    from datetime import datetime, timedelta
    from usage_analytics.services.retell_api_service import RetellAPIService
    from retell_agent.models import RetellAgent
    from ai_agent.models import Chat
    from bookings.models import Booking, serviceTypes
    import json
    
    # Get the business
    business = get_object_or_404(Business, id=business_id)
    
    # Get date range from request parameters
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            # Default to last 30 days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=29)
    except (ValueError, TypeError):
        # Handle invalid date format
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Query bookings for this business within date range
    bookings_in_range = Booking.objects.filter(
        business=business,
        cleaningDate__gte=start_date,
        cleaningDate__lte=end_date
    )
    
    # Count total bookings
    total_bookings = bookings_in_range.count()
    
    # Calculate total revenue
    total_revenue = bookings_in_range.aggregate(
        total=Sum('totalPrice')
    )['total'] or 0
    
    # Get Retell calls for this business
    try:
        # Filter calls for this specific business
        retell_calls = RetellAPIService.list_calls(
            start_date=start_date, 
            end_date=end_date,
            business=business
        )
        total_retell_calls = len(retell_calls)
    except Exception as e:
        print(f"Error fetching Retell calls: {e}")
        total_retell_calls = 0
    
    # Convert date objects to datetime for Chat filtering
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Get chat count for this business
    try:
        total_chats = Chat.objects.filter(
            business=business,
            createdAt__gte=start_datetime, 
            createdAt__lte=end_datetime
        ).count()
    except Exception as e:
        print(f"Error fetching chat count: {e}")
        total_chats = 0
    

    conversion_rate = round((total_bookings/(total_chats + total_retell_calls)) * 100)
    
    # Get distribution data for pie chart (by service type)
    service_type_counts = bookings_in_range.values(
        'serviceType'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    distribution_labels = []
    distribution_values = []
    
    for service in service_type_counts:
        service_name = dict(serviceTypes).get(service['serviceType'], 'Unknown')
        distribution_labels.append(service_name)
        distribution_values.append(service['count'])
    
    # Get time series data
    # Determine appropriate grouping based on date range
    range_days = (end_date - start_date).days + 1
    
    if range_days <= 31:
        # Group by day for ranges up to a month
        time_bookings = bookings_in_range.annotate(
            date=TruncDay('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %d'  # Aug 15
    elif range_days <= 90:
        # Group by week for ranges up to 3 months
        time_bookings = bookings_in_range.annotate(
            date=TruncWeek('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %d'  # Aug 15
    else:
        # Group by month for longer ranges
        time_bookings = bookings_in_range.annotate(
            date=TruncMonth('cleaningDate')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        date_format = '%b %Y'  # Aug 2023
    
    time_series_labels = []
    time_series_values = []
    
    for entry in time_bookings:
        if entry['date']:
            time_series_labels.append(entry['date'].strftime(date_format))
            time_series_values.append(entry['count'])
    
    # Get recent bookings
    recent_bookings = []
    for booking in bookings_in_range.order_by('-createdAt')[:10]:
        status = 'pending'
        if booking.isCompleted:
            status = 'completed'
        elif booking.cancelled_at is not None:
            status = 'cancelled'
        
        service_name = dict(serviceTypes).get(booking.serviceType, 'Other')
        
        recent_bookings.append({
            'id': booking.bookingId,
            'customer_name': f"{booking.firstName} {booking.lastName}",
            'service_type': service_name,
            'date': booking.cleaningDate.strftime('%b %d, %Y'),
            'amount': float(booking.totalPrice),
            'status': status
        })
    
    # Compile response data
    response_data = {
        'total_bookings': total_bookings,
        'total_revenue': float(total_revenue),
        'total_chats': total_chats,
        'total_calls': total_retell_calls,
        'conversion_rate': conversion_rate,
        'distribution_data': {
            'labels': distribution_labels,
            'values': distribution_values
        },
        'time_series_data': {
            'labels': time_series_labels,
            'values': time_series_values
        },
        'recent_bookings': recent_bookings
    }
    
    return JsonResponse(response_data)


# Platform Settings View
@login_required
@user_passes_test(is_admin)
def platform_settings(request):
    # Get or create platform settings
    settings, created = PlatformSettings.objects.get_or_create(pk=1)
    
    if request.method == 'POST':
        # Update platform settings
        settings.setup_fee = 'setup_fee' in request.POST
        settings.setup_fee_amount = request.POST.get('setup_fee_amount', 0)
        settings.company_name = request.POST.get('company_name')
        settings.company_email = request.POST.get('company_email')
        settings.company_phone = request.POST.get('company_phone')
        settings.company_address = request.POST.get('company_address')
        settings.support_email = request.POST.get('support_email')
        settings.default_timezone = request.POST.get('default_timezone')
        settings.maintenance_mode = 'maintenance_mode' in request.POST
        settings.maintenance_message = request.POST.get('maintenance_message')
        settings.updated_by = request.user
        settings.save()
        
        messages.success(request, 'Platform settings have been updated successfully.')
        return redirect('admin_dashboard:platform_settings')
    
    context = {
        'settings': settings,
        'active_tab': 'platform_settings'
    }
    return render(request, 'admin_dashboard/platform_settings.html', context)


# Support Tickets Views
@login_required
@user_passes_test(is_admin)
def support_tickets(request):
    # Get all tickets with filtering
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    category_filter = request.GET.get('category')
    search_query = request.GET.get('q')
    
    tickets = SupportTicket.objects.all()
    
    # Apply filters
    if status_filter and status_filter != 'all':
        tickets = tickets.filter(status=status_filter)
    
    if priority_filter and priority_filter != 'all':
        tickets = tickets.filter(priority=priority_filter)
        
    if category_filter and category_filter != 'all':
        tickets = tickets.filter(category=category_filter)
    
    if search_query:
        tickets = tickets.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(created_by__email__icontains=search_query) |
            Q(created_by__first_name__icontains=search_query) |
            Q(created_by__last_name__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(tickets, 10)  # Show 10 tickets per page
    page_number = request.GET.get('page')
    tickets = paginator.get_page(page_number)
    
    context = {
        'tickets': tickets,
        'status_filter': status_filter or 'all',
        'priority_filter': priority_filter or 'all',
        'category_filter': category_filter or 'all',
        'search_query': search_query or '',
        'active_tab': 'support_tickets'
    }
    return render(request, 'admin_dashboard/support_tickets.html', context)


@login_required
@user_passes_test(is_admin)
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    comments = ticket.comments.all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            new_status = request.POST.get('status')
            ticket.status = new_status
            
            # Set resolved_at if status is changed to resolved
            if new_status == 'resolved' and ticket.resolved_at is None:
                ticket.resolved_at = timezone.now()
            
            # Clear resolved_at if status is changed from resolved
            if new_status != 'resolved':
                ticket.resolved_at = None
                
            ticket.save()
            messages.success(request, f'Ticket status updated to {ticket.get_status_display()}')
            
        elif action == 'update_priority':
            ticket.priority = request.POST.get('priority')
            ticket.save()
            messages.success(request, f'Ticket priority updated to {ticket.get_priority_display()}')
            
        elif action == 'assign':
            user_id = request.POST.get('assigned_to')
            if user_id:
                assigned_user = get_object_or_404(User, id=user_id)
                ticket.assigned_to = assigned_user
                ticket.save()
                messages.success(request, f'Ticket assigned to {assigned_user.get_full_name()}')
            else:
                ticket.assigned_to = None
                ticket.save()
                messages.success(request, 'Ticket unassigned')
                
        elif action == 'add_comment':
            content = request.POST.get('content')
            is_internal = 'is_internal' in request.POST
            
            if content:
                comment = TicketComment.objects.create(
                    ticket=ticket,
                    author=request.user,
                    content=content,
                    is_internal=is_internal
                )
                
                # Handle attachment if provided
                if 'attachment' in request.FILES:
                    comment.attachment = request.FILES['attachment']
                    comment.save()
                
                messages.success(request, 'Comment added successfully')
            else:
                messages.error(request, 'Comment content cannot be empty')
    
    # Get all staff users for assignment
    staff_users = User.objects.filter(is_staff=True).order_by('first_name')
    
    context = {
        'ticket': ticket,
        'comments': comments,
        'staff_users': staff_users,
        'active_tab': 'support_tickets'
    }
    return render(request, 'admin_dashboard/ticket_detail.html', context)

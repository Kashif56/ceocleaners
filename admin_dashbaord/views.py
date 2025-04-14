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
    
    context = {
        'total_businesses': total_businesses,
        'active_subscriptions': active_subscriptions,
        'pending_approvals': pending_approvals,
        'monthly_revenue': monthly_revenue,
        'recent_businesses': recent_businesses,
        'recent_subscriptions': recent_subscriptions,
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
        price = request.POST.get('price')
        billing_cycle = request.POST.get('billing_cycle')
        voice_minutes = request.POST.get('voice_minutes')
        sms_messages = request.POST.get('sms_messages')
        agents = request.POST.get('agents')
        leads = request.POST.get('leads')
        cleaners = request.POST.get('cleaners')
        is_active = 'is_active' in request.POST
        
        # Create plan
        plan = SubscriptionPlan.objects.create(
            name=name,
            price=price,
            billing_cycle=billing_cycle,
            voice_minutes=voice_minutes,
            sms_messages=sms_messages,
            agents=agents,
            leads=leads,
            cleaners=cleaners,
            is_active=is_active
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
                name=name,
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
        plan.price = request.POST.get('price')
        plan.billing_cycle = request.POST.get('billing_cycle')
        plan.voice_minutes = request.POST.get('voice_minutes')
        plan.sms_messages = request.POST.get('sms_messages')
        plan.agents = request.POST.get('agents')
        plan.leads = request.POST.get('leads')
        plan.cleaners = request.POST.get('cleaners')
        plan.is_active = 'is_active' in request.POST
        
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
            corresponding_plan = SubscriptionPlan.objects.get(
                name=plan.name,
                billing_cycle=other_billing_cycle
            )
            
            # Synchronize features
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
    businesses = Business.objects.all().order_by('-createdAt')
    
    # Add active subscription to each business
    for business in businesses:
        try:
            business.active_subscription = BusinessSubscription.objects.filter(
                business=business, 
                status='active'
            ).latest('start_date')
        except BusinessSubscription.DoesNotExist:
            business.active_subscription = None
    
    # Pagination
    paginator = Paginator(businesses, 10)
    page_number = request.GET.get('page', 1)
    businesses = paginator.get_page(page_number)
    
    # Get all users for the add business form
    users = User.objects.all().order_by('username')
    
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

    print(business.all_subscriptions)
    
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
        business.phone = request.POST.get('phone')
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

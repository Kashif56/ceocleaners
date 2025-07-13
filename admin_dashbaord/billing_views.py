from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse

from accounts.models import Business
from subscription.models import BillingHistory, BusinessSubscription

from .views import is_admin as is_admin_user


@login_required
@user_passes_test(is_admin_user)
def billing_history_list(request):
    """View for displaying all billing history records"""
    # Get query parameters for filtering
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Start with all billing records
    billing_records = BillingHistory.objects.all().order_by('-billing_date')
    
    # Apply filters
    if search_query:
        billing_records = billing_records.filter(
            Q(business__businessName__icontains=search_query) |
            Q(business__businessId__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    if status_filter:
        billing_records = billing_records.filter(status=status_filter)
    
    if date_from:
        billing_records = billing_records.filter(billing_date__gte=date_from)
    
    if date_to:
        billing_records = billing_records.filter(billing_date__lte=date_to)
    
    # Pagination
    paginator = Paginator(billing_records, 20)  # Show 20 records per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get unique statuses for filter dropdown
    statuses = BillingHistory.STATUS_CHOICES
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'statuses': statuses,
        'total_records': billing_records.count(),
    }
    
    return render(request, 'admin_dashboard/billing_history_list.html', context)


@login_required
@user_passes_test(is_admin_user)
def billing_history_detail(request, billing_id):
    """View for displaying details of a specific billing record"""
    billing_record = get_object_or_404(BillingHistory, id=billing_id)
    
    # Get related subscription and business
    subscription = billing_record.subscription
    business = billing_record.business
    
    context = {
        'billing': billing_record,
        'subscription': subscription,
        'business': business,
    }
    
    return render(request, 'admin_dashboard/billing_history_detail.html', context)


@login_required
@user_passes_test(is_admin_user)
def business_billing_history(request, business_id):
    """View for displaying billing history for a specific business"""
    business = get_object_or_404(Business, id=business_id)
    
    # Get all billing records for this business
    billing_records = BillingHistory.objects.filter(business=business).order_by('-billing_date')
    
    # Pagination
    paginator = Paginator(billing_records, 10)  # Show 10 records per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'business': business,
        'page_obj': page_obj,
        'total_records': billing_records.count(),
    }
    
    return render(request, 'admin_dashboard/business_billing_history.html', context)


@login_required
@user_passes_test(is_admin_user)
def subscription_billing_history(request, subscription_id):
    """View for displaying billing history for a specific subscription"""
    subscription = get_object_or_404(BusinessSubscription, id=subscription_id)
    
    # Get all billing records for this subscription
    billing_records = BillingHistory.objects.filter(subscription=subscription).order_by('-billing_date')
    
    # Pagination
    paginator = Paginator(billing_records, 10)  # Show 10 records per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'subscription': subscription,
        'page_obj': page_obj,
        'total_records': billing_records.count(),
    }
    
    return render(request, 'admin_dashboard/subscription_billing_history.html', context)

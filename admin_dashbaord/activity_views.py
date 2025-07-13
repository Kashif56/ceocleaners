from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.models import User
from .models import ActivityLog

# Helper function to check if user is admin
def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def activity_logs(request):
    """View to display activity logs with filtering"""
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
    
    # Advanced filtering options
    # Filter by IP address
    ip_address = request.GET.get('ip_address', '')
    if ip_address:
        logs = logs.filter(ip_address__icontains=ip_address)
    
    # Filter by content type
    content_type = request.GET.get('content_type', '')
    if content_type:
        logs = logs.filter(content_type__model=content_type)
    
    # Filter by object ID
    object_id = request.GET.get('object_id', '')
    if object_id:
        logs = logs.filter(object_id=object_id)
    
    # Get all users for the filter dropdown
    users = User.objects.all().order_by('username')
    
    # Get all activity types for the filter dropdown
    activity_types = dict(ActivityLog.ACTIVITY_TYPES)
    
    # Get content types for filtering
    from django.contrib.contenttypes.models import ContentType
    content_types = ContentType.objects.filter(
        id__in=ActivityLog.objects.values_list('content_type', flat=True).distinct()
    ).exclude(id__isnull=True)
    
    # Sort options
    sort_by = request.GET.get('sort_by', '-timestamp')
    valid_sort_fields = ['timestamp', '-timestamp', 'user__username', '-user__username', 
                         'activity_type', '-activity_type', 'ip_address', '-ip_address']
    
    if sort_by in valid_sort_fields:
        logs = logs.order_by(sort_by)
    else:
        logs = logs.order_by('-timestamp')  # Default sorting
    
    # Pagination
    paginator = Paginator(logs, 20)  # Show 20 logs per page
    page_number = request.GET.get('page', 1)
    logs = paginator.get_page(page_number)
    
    context = {
        'logs': logs,
        'users': users,
        'activity_types': activity_types,
        'content_types': content_types,
        'selected_activity_type': activity_type,
        'selected_user_id': user_id,
        'selected_content_type': content_type,
        'selected_object_id': object_id,
        'selected_ip_address': ip_address,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    
    return render(request, 'admin_dashboard/activity_logs.html', context)

@login_required
@user_passes_test(is_admin)
def activity_log_detail(request, log_id):
    """View to display details of a specific activity log"""
    log = get_object_or_404(ActivityLog, id=log_id)
    
    # Get related logs from the same user
    related_user_logs = ActivityLog.objects.filter(
        user=log.user
    ).exclude(id=log.id).order_by('-timestamp')[:5]
    
    # Get related logs of the same type
    related_type_logs = ActivityLog.objects.filter(
        activity_type=log.activity_type
    ).exclude(id=log.id).order_by('-timestamp')[:5]
    
    # Get related logs for the same content object (if applicable)
    related_object_logs = []
    if log.content_type and log.object_id:
        related_object_logs = ActivityLog.objects.filter(
            content_type=log.content_type,
            object_id=log.object_id
        ).exclude(id=log.id).order_by('-timestamp')[:5]
    
    context = {
        'log': log,
        'related_user_logs': related_user_logs,
        'related_type_logs': related_type_logs,
        'related_object_logs': related_object_logs,
    }
    
    return render(request, 'admin_dashboard/activity_log_detail.html', context)

@login_required
@user_passes_test(is_admin)
def user_activity_logs(request, user_id):
    """View to display all activity logs for a specific user"""
    user = get_object_or_404(User, id=user_id)
    
    # Get all logs for this user
    logs = ActivityLog.objects.filter(user=user)
    
    # Filter by activity type
    activity_type = request.GET.get('activity_type', '')
    if activity_type:
        logs = logs.filter(activity_type=activity_type)
    
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
    
    # Get all activity types for the filter dropdown
    activity_types = dict(ActivityLog.ACTIVITY_TYPES)
    
    # Pagination
    paginator = Paginator(logs, 20)  # Show 20 logs per page
    page_number = request.GET.get('page', 1)
    logs = paginator.get_page(page_number)
    
    context = {
        'user_profile': user,
        'logs': logs,
        'activity_types': activity_types,
        'selected_activity_type': activity_type,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
    }
    
    return render(request, 'admin_dashboard/user_activity_logs.html', context)

@login_required
@user_passes_test(is_admin)
def export_activity_logs(request):
    """Export activity logs as CSV based on filters"""
    import csv
    from django.http import HttpResponse
    
    # Get all activity logs with filters applied
    logs = ActivityLog.objects.all()
    
    # Apply the same filters as in the activity_logs view
    activity_type = request.GET.get('activity_type', '')
    if activity_type:
        logs = logs.filter(activity_type=activity_type)
    
    user_id = request.GET.get('user_id', '')
    if user_id:
        logs = logs.filter(user_id=user_id)
    
    start_date = request.GET.get('start_date', '')
    if start_date:
        logs = logs.filter(timestamp__gte=start_date)
    
    end_date = request.GET.get('end_date', '')
    if end_date:
        logs = logs.filter(timestamp__lte=end_date + ' 23:59:59')
    
    search_query = request.GET.get('search', '')
    if search_query:
        logs = logs.filter(description__icontains=search_query)
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="activity_logs.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    writer.writerow(['ID', 'User', 'Activity Type', 'Description', 'IP Address', 'Timestamp', 'Content Type', 'Object ID'])
    
    # Add data to CSV
    for log in logs:
        content_type_str = log.content_type.model if log.content_type else ''
        writer.writerow([
            log.id,
            log.user.username,
            log.get_activity_type_display(),
            log.description,
            log.ip_address or '',
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            content_type_str,
            log.object_id or ''
        ])
    
    return response

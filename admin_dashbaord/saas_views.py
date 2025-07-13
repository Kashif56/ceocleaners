from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from accounts.models import User
from saas.models import PlatformSettings, SupportTicket, TicketComment

# Helper function to check if user is admin
def is_admin(user):
    return user.is_staff or user.is_superuser


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
    
    tickets = SupportTicket.objects.all().order_by('-created_at')
    
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
    comments = ticket.comments.all().order_by('created_at')
    
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
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import PlatformSettings, SupportTicket, TicketComment
from accounts.models import User, Business


def maintenance_view(request):
    """
    View to display maintenance page when the site is in maintenance mode.
    """
    try:
        settings = PlatformSettings.objects.get(pk=1)
        maintenance_message = settings.maintenance_message
    except PlatformSettings.DoesNotExist:
        maintenance_message = "Site is under maintenance. Please check back later."
    
    maintenance_mode = settings.maintenance_mode
    
    if not maintenance_mode:
        return redirect('home')
        
    context = {
        'maintenance_message': maintenance_message
    }
    return render(request, 'maintenance.html', context)

# User-facing support ticket submission view
@login_required
def submit_ticket(request):
    if request.method == 'POST':
        # Create a new ticket from form data
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        priority = request.POST.get('priority')
        url = request.POST.get('url')
        
        # Create the ticket
        ticket = SupportTicket(
            title=title,
            description=description,
            category=category,
            priority=priority,
            url=url,
            created_by=request.user,
            status='new'
        )
        
        # Associate with business if user has one
        if hasattr(request.user, 'business'):
            ticket.business = request.user.business
        
        # Capture browser info
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        ticket.browser_info = user_agent
        
        # Handle screenshot if provided
        if 'screenshot' in request.FILES:
            ticket.screenshot = request.FILES['screenshot']
        
        ticket.save()
        messages.success(request, 'Your support ticket has been submitted successfully. We will get back to you soon.')
        return redirect('saas:my_tickets')
    
    context = {
        'title': 'Submit Support Ticket'
    }
    return render(request, 'support/submit_ticket.html', context)


@login_required
def my_tickets(request):
    # Get tickets for the current user
    tickets = SupportTicket.objects.filter(created_by=request.user).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(tickets, 10)  # Show 10 tickets per page
    page_number = request.GET.get('page')
    tickets = paginator.get_page(page_number)
    
    context = {
        'tickets': tickets,
        'title': 'My Support Tickets'
    }
    return render(request, 'support/my_tickets.html', context)


@login_required
def ticket_detail(request, ticket_id):
    # Ensure the user can only view their own tickets
    ticket = get_object_or_404(SupportTicket, id=ticket_id, created_by=request.user)
    comments = ticket.comments.filter(is_internal=False)  # Don't show internal notes to users
    
    if request.method == 'POST':
        # Add a comment to the ticket
        content = request.POST.get('content')
        
        if content:
            comment = TicketComment.objects.create(
                ticket=ticket,
                author=request.user,
                content=content,
                is_internal=False  # User comments are never internal
            )
            
            # Handle attachment if provided
            if 'attachment' in request.FILES:
                comment.attachment = request.FILES['attachment']
                comment.save()
            
            messages.success(request, 'Your comment has been added successfully.')
        else:
            messages.error(request, 'Comment content cannot be empty.')
    
    context = {
        'ticket': ticket,
        'comments': comments,
        'title': f'Ticket #{ticket.id}: {ticket.title}'
    }
    return render(request, 'support/ticket_detail.html', context)

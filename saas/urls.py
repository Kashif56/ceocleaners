from django.urls import path
from . import views

app_name = 'saas'

urlpatterns = [
    # Support ticket URLs
    path('support/submit-ticket/', views.submit_ticket, name='submit_ticket'),
    path('support/my-tickets/', views.my_tickets, name='my_tickets'),
    path('support/tickets/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    
    # Maintenance mode URL
    path('maintenance/', views.maintenance_view, name='maintenance'),
]

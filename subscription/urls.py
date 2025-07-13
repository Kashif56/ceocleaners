from django.urls import path
from . import views

app_name = 'subscription'

urlpatterns = [
    path('', views.subscription_management, name='subscription_management'),
    path('billing-history/', views.billing_history, name='billing_history'),
    path('change-plan/', views.change_plan, name='change_plan'),
    path('cancel-plan-change/', views.cancel_plan_change, name='cancel_plan_change'),
    path('cancel/', views.cancel_subscription, name='cancel_subscription'),
    path('api/subscription-data/', views.get_subscription_data, name='get_subscription_data'),
    
    # New payment URLs
    path('select-plan/', views.select_plan, name='select_plan'),
    path('select-plan/<int:plan_id>/', views.select_plan, name='select_plan'),
    path('process-payment/<int:plan_id>/', views.process_payment, name='process_payment'),
    path('success/<int:subscription_id>/<str:transaction_id>/', views.subscription_success, name='subscription_success'),
    path('trial-success/<int:subscription_id>/', views.trial_success, name='trial_success'),
    path('onboarding-call-success/', views.onboarding_call_success, name='onboarding_call_success'),
    
    # Coupon validation
    path('validate-coupon/', views.validate_coupon, name='validate_coupon'),
    path('update-auto-upgrade/', views.update_auto_upgrade, name='update_auto_upgrade'),
    path('manage-card/', views.manage_card, name='manage_card'),  # New URL for card management
    path('delete-card/', views.delete_card, name='delete_card'),
]

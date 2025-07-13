from django.urls import path
from . import views
from . import saas_views
from . import billing_views
from . import activity_views

app_name = 'admin_dashboard'

urlpatterns = [
    # Dashboard index
    path('', views.dashboard_index, name='index'),
    
    # Analytics Dashboard
    path('analytics/', views.analytics, name='analytics'),
    path('api/analytics/', views.api_analytics, name='api_analytics'),
    
    # Business Analytics
    path('businesses/<int:business_id>/analytics/', views.business_analytics, name='business_analytics'),
    path('api/business-analytics/<int:business_id>/', views.business_analytics_api, name='business_analytics_api'),
    
    # Subscription Plans
    path('subscription-plans/', views.subscription_plans, name='subscription_plans'),
    path('subscription-plans/add/', views.add_plan, name='add_plan'),
    path('subscription-plans/edit/', views.edit_plan, name='edit_plan'),
    path('subscription-plans/delete/', views.delete_plan, name='delete_plan'),
    
    # Features
    path('features/', views.features, name='features'),
    path('features/add/', views.add_feature, name='add_feature'),
    path('features/edit/', views.edit_feature, name='edit_feature'),
    path('features/delete/', views.delete_feature, name='delete_feature'),
    
    # Coupons
    path('coupons/', views.coupons, name='coupons'),
    path('coupons/add/', views.add_coupon, name='add_coupon'),
    path('coupons/edit/', views.edit_coupon, name='edit_coupon'),
    path('coupons/delete/', views.delete_coupon, name='delete_coupon'),
    
    # Businesses
    path('businesses/', views.businesses, name='businesses'),
    path('businesses/add/', views.add_business, name='add_business'),
    path('businesses/edit/', views.edit_business, name='edit_business'),
    path('businesses/approve/', views.approve_business, name='approve_business'),
    path('businesses/reject/', views.reject_business, name='reject_business'),
    path('businesses/delete/', views.delete_business, name='delete_business'),
    path('businesses/export/', views.export_businesses, name='export_businesses'),
    path('businesses/<int:business_id>/', views.business_detail, name='business_detail'),
    path('businesses/edit-api-credentials/', views.edit_api_credentials, name='edit_api_credentials'),
    
    # Subscription Management
    path('subscriptions/', views.subscriptions, name='subscriptions'),
    path('subscriptions/<int:subscription_id>/', views.subscription_detail, name='subscription_detail'),
    path('subscriptions/assign/', views.assign_subscription, name='assign_subscription'),
    path('subscriptions/admin-cancel-plan/', views.admin_cancel_plan, name='admin_cancel_plan'),
    
    # Platform Settings
    path('platform-settings/', saas_views.platform_settings, name='platform_settings'),
    
    # Support Tickets
    path('support-tickets/', saas_views.support_tickets, name='support_tickets'),
    path('support-tickets/<int:ticket_id>/', saas_views.ticket_detail, name='ticket_detail'),
    path('subscriptions/admin-change-plan/', views.admin_change_plan, name='admin_change_plan'),
    
    # User Management
    path('users/', views.users, name='users'),
    path('users/add/', views.add_user, name='add_user'),
    path('users/edit/', views.edit_user, name='edit_user'),
    path('users/delete/', views.delete_user, name='delete_user'),
    
    # Activity Logs
    path('activity-logs/', activity_views.activity_logs, name='activity_logs'),
    path('activity-logs/<int:log_id>/', activity_views.activity_log_detail, name='activity_log_detail'),
    path('activity-logs/user/<int:user_id>/', activity_views.user_activity_logs, name='user_activity_logs'),
    path('activity-logs/export/', activity_views.export_activity_logs, name='export_activity_logs'),
    
    # Billing History
    path('billing-history/', billing_views.billing_history_list, name='billing_history_list'),
    path('billing-history/<int:billing_id>/', billing_views.billing_history_detail, name='billing_history_detail'),
    path('businesses/<int:business_id>/billing-history/', billing_views.business_billing_history, name='business_billing_history'),
    path('subscriptions/<int:subscription_id>/billing-history/', billing_views.subscription_billing_history, name='subscription_billing_history'),
]
from django.urls import path
from . import views
from . import thumbtack_views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.loginPage, name='login'),
    path('register/', views.SignupPage, name='signup'),
    path('logout/', views.logoutUser, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/test-email/', views.test_email_settings, name='test_email_settings'),
    path('register-business/', views.register_business, name='register_business'),
    path('business/edit/', views.edit_business, name='edit_business'),
    path('business/settings/edit/', views.edit_business_settings, name='edit_business_settings'),
    path('custom-addon/add/', views.add_custom_addon, name='add_custom_addon'),
    path('custom-addon/<int:addon_id>/edit/', views.edit_custom_addon, name='edit_custom_addon'),
    path('custom-addon/<int:addon_id>/delete/', views.delete_custom_addon, name='delete_custom_addon'),
    path('business/credentials/edit/', views.edit_credentials, name='edit_credentials'),
    path('business/credentials/generate-secret/', views.generate_secret_key, name='generate_secret_key'),
    path('business/credentials/regenerate-secret/', views.regenerate_secret_key, name='regenerate_secret_key'),
   
    
    # Password Reset URLs
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-otp/<str:email>/', views.verify_otp, name='verify_otp'),
    path('resend-otp/<str:email>/', views.resend_otp, name='resend_otp'),
    path('reset-password/<str:email>/<str:token>/', views.reset_password, name='reset_password'),
    
    # SMTP Configuration URLs
    path('smtp-config/', views.smtp_config, name='smtp_config'),
    path('smtp-config/delete/', views.delete_smtp_config, name='delete_smtp_config'),
    
    # Approval Pending URL
    path('approval-pending/', views.approval_pending, name='approval_pending'),
    



    path('update-business-settings/', views.update_business_settings, name='update_business_settings'),
    
   
    path('payments/square/', views.payment_square_view, name='payment_square'),
    path('payments/square/manage/', views.manage_square_credentials, name='manage_square_credentials'),
    
    # Payment Main Page
    path('payments/', views.payment_main_view, name='payment_main'),
    
    # Set Default Payment Method
    path('payments/set-default/', views.set_default_payment, name='set_default_payment'),
    
    # Stripe Payment URLs
    path('payments/stripe/', views.payment_stripe_view, name='payment_stripe'),
    path('payments/stripe/manage/', views.manage_stripe_credentials, name='manage_stripe_credentials'),
    
    # PayPal Payment URLs
    path('payments/paypal/', views.payment_paypal_view, name='payment_paypal'),
    path('payments/paypal/manage/', views.manage_paypal_credentials, name='manage_paypal_credentials'),
    
    # Cleaner Management URLs
    path('cleaners/', views.manage_cleaners, name='manage_cleaners'),
    path('cleaners/<int:cleaner_id>/register/', views.register_cleaner_user, name='register_cleaner_user'),
    path('cleaners/<int:cleaner_id>/', views.cleaner_detail, name='cleaner_detail'),
    path('cleaners/<int:cleaner_id>/edit-account/', views.edit_cleaner_account, name='edit_cleaner_account'),
    path('cleaners/reset-password/', views.reset_cleaner_password, name='reset_cleaner_password'),
    path('cleaners/change-password/', views.cleaner_change_password, name='cleaner_change_password'),


    # Thumbtack URLs
    path('thumbtack/connect/', thumbtack_views.thumbtack_connect, name='thumbtack_connect'),
    path('thumbtack/disconnect/', thumbtack_views.thumbtack_disconnect, name='thumbtack_disconnect'),
    path('thumbtack/callback/', thumbtack_views.thumbtack_callback_prod, name='thumbtack_callback_prod'),
    path('thumbtack/profile/', thumbtack_views.thumbtack_profile, name='thumbtack_profile'),
    path('thumbtack/dashboard/', thumbtack_views.thumbtack_dashboard, name='thumbtack_dashboard'),
    path('thumbtack/settings/', thumbtack_views.thumbtack_settings, name='thumbtack_settings'),
]
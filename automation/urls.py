from django.urls import path
from . import views
from .webhooks import handle_retell_webhook, thumbtack_webhook, chatgpt_analysis_webhook
from .api_views import check_availability_retell, test_check_availability, check_availability_for_booking, create_booking, sendCommercialFormLink, reschedule_booking, cancel_booking
from . import twilio_views



urlpatterns = [
    path('', views.LandingPage, name='landing-page'),
    path('pricing/', views.PricingPage, name='pricing-page'),
    path('features/', views.FeaturesPage, name='features-page'),
    path('about-us/', views.AboutUsPage, name='about-us'),
    path('contact-us/', views.ContactUsPage, name='contact-us'),
    path('docs/', views.DocsPage, name='docs-page'),
    path('dashboard/', views.home, name='home'),
    path('webhook/<str:secretKey>/', handle_retell_webhook, name='retell_webhook'),
    path('webhook/thumbtack/<str:secretKey>/', thumbtack_webhook, name='thumbtack_webhook'),
    path('lead/webhook/<str:secretKey>/', chatgpt_analysis_webhook, name='chatgpt_analysis_webhook'),

    # Lead Management URLs
    path('leads/', views.all_leads, name='all_leads'),
    path('leads/create/', views.create_lead, name='create_lead'),
    path('leads/<str:leadId>/', views.lead_detail, name='lead_detail'),
    path('leads/<str:leadId>/update/', views.update_lead, name='update_lead'),
    path('leads/<str:leadId>/delete/', views.delete_lead, name='delete_lead'),

    # API endpoints
    path('api/availability/<str:secretKey>/', check_availability_retell, name='check_availability'),
    path('api/availability/<str:secretKey>/test/', test_check_availability, name='test_check_availability'),
    path('api/check-availability/', check_availability_for_booking, name='check_availability_for_booking'),
    path('api/reschedule-booking/', reschedule_booking, name='reschedule_booking'),
    path('api/cancel-booking/', cancel_booking, name='cancel_booking'),


    path('api/create-booking/', create_booking, name='create_booking'),
    path('api/send-commercial-form-link/', sendCommercialFormLink, name='send_commercial_form_link'),
    path('bulk-delete-leads/', views.bulk_delete_leads, name='bulk_delete_leads'),
   
    
    # Test pages
    path('test/', views.test_features, name='test_features'),
    path('test/availability/', views.test_availability_api, name='test_availability_api'),

   
    # Cleaners URLs
    path('cleaners/', views.cleaners_list, name='cleaners_list'),
    path('cleaners/add/', views.add_cleaner, name='add_cleaner'),
    path('cleaners/<int:cleaner_id>/', views.cleaner_detail, name='cleaner_detail'),
    path('cleaners/<int:cleaner_id>/monthly-schedule/', views.cleaner_monthly_schedule, name='cleaner_monthly_schedule'),
    path('cleaners/<int:cleaner_id>/update-profile/', views.update_cleaner_profile, name='update_cleaner_profile'),
    path('cleaners/<int:cleaner_id>/update-schedule/', views.update_cleaner_schedule, name='update_cleaner_schedule'),
    path('cleaners/<int:cleaner_id>/add-specific-date/', views.add_specific_date, name='add_specific_date'),
    path('cleaners/<int:cleaner_id>/delete-specific-date/<int:exception_id>/', views.delete_specific_date, name='delete_specific_date'),
    path('cleaners/<int:cleaner_id>/toggle-availability/', views.toggle_cleaner_availability, name='toggle_cleaner_availability'),
    path('cleaners/<int:cleaner_id>/toggle-active/', views.toggle_cleaner_active, name='toggle_cleaner_active'),
    path('cleaners/<int:cleaner_id>/delete/', views.delete_cleaner, name='delete_cleaner'),
    path('cleaners/<int:cleaner_id>/update-login/', views.update_cleaner_login, name='update_cleaner_login'),
    
    # Open Jobs URLs
    path('cleaners/<int:cleaner_id>/jobs/', views.open_jobs, name='cleaner_open_jobs'),
    path('jobs/<str:job_id>/accept/', views.accept_open_job, name='accept_open_job'),
    path('jobs/<str:job_id>/reject/', views.reject_open_job, name='reject_open_job'),

    # Business Schedule URLs
    path('business-schedule/', views.business_monthly_schedule, name='business_monthly_schedule'),

    # reCAPTCHA verification endpoint
    path('verify-recaptcha/', views.verify_recaptcha, name='verify_recaptcha'),

    # Demo booking form
    path('book-demo/', views.book_demo, name='book_demo'),

    # Privacy Policy and Terms of Service
    path('privacy-policy/', views.PrivacyPolicyPage, name='privacy_policy'),
    path('terms-of-service/', views.TermsOfServicePage, name='terms_of_service'),
    path('sitemap/', views.sitemap, name='sitemap'),
    
    # Booking status updates
    path('<str:booking_id>/confirm-arrival/', views.confirm_arrival, name='confirm_arrival'),
    path('<str:booking_id>/confirm-completed/', views.confirm_completed, name='confirm_completed'),

    # Twilio URLs
    path('twilio/phone-numbers/', twilio_views.twilio_phone_numbers, name='twilio_phone_numbers'),
    path('twilio/phone-numbers/search/', twilio_views.search_twilio_numbers, name='search_twilio_numbers'),
    path('twilio/phone-numbers/purchase/', twilio_views.purchase_twilio_number, name='purchase_twilio_number'),
    path('twilio/phone-numbers/get/', twilio_views.get_twilio_numbers, name='get_twilio_numbers'),
    path('twilio/phone-numbers/update-webhook/', twilio_views.update_twilio_webhook, name='update_twilio_webhook'),
    path('twilio/phone-numbers/set-active/', twilio_views.set_active_number, name='set_active_number'),

]
from django.urls import path
from . import views

app_name = 'usage_analytics'

urlpatterns = [
    path('', views.usage_overview, name='usage_overview'),
    path('voice/', views.voice_analytics, name='voice_analytics'),
    path('sms/', views.sms_analytics, name='sms_analytics'),
    path('api/usage-data/', views.get_usage_data, name='get_usage_data'),
    path('api/voice-analytics/', views.get_voice_analytics, name='get_voice_analytics'),
    path('api/call-volume/', views.get_call_volume, name='get_call_volume'),
    path('api/call-outcomes/', views.get_call_outcomes, name='get_call_outcomes'),
    path('api/call-duration-distribution/', views.get_call_duration_distribution, name='get_call_duration_distribution'),
    path('api/call-success-rate/', views.get_call_success_rate, name='get_call_success_rate'),
    path('api/disconnection-reasons/', views.get_disconnection_reasons, name='get_disconnection_reasons'),
    path('api/sentiment-distribution/', views.get_sentiment_distribution, name='get_sentiment_distribution'),
    path('api/call-success-distribution/', views.get_call_success_distribution, name='get_call_success_distribution'),
    path('api/recent-calls/', views.get_recent_calls, name='get_recent_calls'),
    path('api/sms-analytics/', views.get_sms_analytics, name='get_sms_analytics'),
    path('api/sms-volume/', views.get_sms_volume, name='get_sms_volume'),
    path('api/sms-response-rate/', views.get_sms_response_rate, name='get_sms_response_rate'),
    path('api/sms-response-time/', views.get_sms_response_time, name='get_sms_response_time'),
    path('api/recent-sms-messages/', views.get_recent_sms_messages, name='get_recent_sms_messages'),
]

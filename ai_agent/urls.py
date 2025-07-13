from django.urls import path
from . import views, openai_agent

app_name = 'ai_agent'

urlpatterns = [
    # OpenAI-based chatbot endpoints (primary endpoints)
    path('chat/', openai_agent.chat_view, name='chat_view'),
    path('api/chat/', openai_agent.chat_api, name='chat_api'),
    path('api/chat/<str:client_phone_number>/delete/', openai_agent.delete_chat, name='delete_chat'),
    
    # Legacy OpenAI-based chatbot endpoints (keeping for backward compatibility)
    path('openai-chat/', openai_agent.chat_view, name='openai_chat_view'),
    path('api/openai-chat/', openai_agent.chat_api, name='openai_chat_api'),
    path('api/openai-chat/<str:client_phone_number>/delete/', openai_agent.delete_chat, name='openai_delete_chat'),
    
    # Twilio webhook URL
    path('api/twilio/webhook/<str:secretKey>/', views.twilio_webhook, name='twilio_webhook'),

    # New unified agent configuration pages
    path('agent-config/', views.agent_config_unified, name='agent_config'),
    path('agent-config/save/', views.agent_config_save, name='agent_config_save'),
    path('embed-agent/', views.embed_agent, name='embed_agent'),
    
    # Business credentials API
    path('api/business/credentials/', views.business_credentials_api, name='business_credentials_api'),
    
    # New SMS chat management views
    path('sms-chats/', views.all_chats, name='all_chats'),
    path('api/sms-chats/delete/', views.delete_chat, name='delete_sms_chat'),
    path('chat/<int:chat_id>/data', views.get_chat_data, name='get_chat_data'),
]

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static




urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('automation.urls')),
    path('accounts/', include('accounts.urls')),
    path('booking/', include('bookings.urls')),
    path('invoice/', include('invoice.urls')),
    path('integration/', include('integrations.urls')),
    path('analytics/', include('analytics.urls')),
    path('ai_agent/', include('ai_agent.urls')),
    path('usage_analytics/', include('usage_analytics.urls')),
    path('subscription/', include('subscription.urls')),
    path('voice_agent/', include('retell_agent.urls')),
    path('admin-dashboard/', include('admin_dashbaord.urls')),
    path('saas/', include('saas.urls')),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG == False:
    handler400 = 'leadsAutomation.error_handlers.handler400'
    handler403 = 'leadsAutomation.error_handlers.handler403'
    handler404 = 'leadsAutomation.error_handlers.handler404'
    handler500 = 'leadsAutomation.error_handlers.handler500'
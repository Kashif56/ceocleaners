from django.contrib import admin
from .models import PlatformSettings, SupportTicket, TicketComment

admin.site.register(PlatformSettings)
admin.site.register(SupportTicket)
admin.site.register(TicketComment)


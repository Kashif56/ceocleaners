from django.apps import AppConfig


class AdminDashbaordConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_dashbaord'
    
    def ready(self):
        """
        Import signals when the app is ready
        This ensures that the signal handlers are registered
        """
        import admin_dashbaord.signals

from django.db import models

# Here SaaS Platform Related Mdoels like Platform Settings will be Created to Give More Control to Admin to Enable or Disable 

class PlatformSettings(models.Model):
    setup_fee = models.BooleanField(default=True)
    setup_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    
    

    def __str__(self):
        return f"Platform Settings"


from .models import ApiCredential
from django.db.models.signals import post_save
from django.dispatch import receiver
from retell_agent.api import RetellAgentAPI
from retell_agent.models import RetellAgent
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from accounts.models import Business, CleanerProfile, ApiCredential
from automation.models import Cleaners
from django.apps import apps
from dotenv import load_dotenv
import os

load_dotenv()
twilio_sid = os.getenv('TWILIO_SID')
twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')

@receiver(post_save, sender=ApiCredential)
def update_api_credential(sender, instance, **kwargs):
    if instance.id:
        payload = {
            'webhook_url' : instance.getRetellUrl()
        }

        retell_agent = RetellAgent.objects.filter(business=instance.business).first()
        if retell_agent:
            RetellAgentAPI.update_agent(retell_agent.agent_id, payload)
        


@receiver(post_save, sender=CleanerProfile)
def assign_cleaner_group(sender, instance, created, **kwargs):
    """
    Assign the Cleaner group to users with cleaner profiles
    """
    if instance.user:
        try:
            cleaner_group, created = Group.objects.get_or_create(name='Cleaner')
            instance.user.groups.add(cleaner_group)
        except Exception as e:
            print(f"Error assigning cleaner group: {e}")

@receiver(post_save, sender=Business)
def assign_owner_group(sender, instance, created, **kwargs):
    """
    Assign the Owner group to users with businesses
    """
    if instance.user:
        try:
            owner_group, created = Group.objects.get_or_create(name='Owner')
            instance.user.groups.add(owner_group)
        except Exception as e:
            print(f"Error assigning owner group: {e}")
        

# @receiver(post_save, sender=Business)
# def add_twilio_credentials(sender, instance, created, **kwargs):
#     if created:
#         api_credential, created = ApiCredential.objects.get_or_create(business=instance)
#         if created:
#             api_credential.twilioAccountSid = twilio_sid
#             api_credential.twilioAuthToken = twilio_auth_token
#             api_credential.save()
    
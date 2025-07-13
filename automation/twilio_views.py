import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from accounts.models import ApiCredential, Business
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

@login_required
def twilio_phone_numbers(request):
    """
    View for managing Twilio phone numbers
    """
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
        api_credential = ApiCredential.objects.create(business=business)
    
    context = {
        'business': business,
        'api_credential': api_credential,
    }
    
    return render(request, 'automation/twilio_phone_numbers.html', context)

@login_required
def search_twilio_numbers(request):
    """
    API endpoint to search for available Twilio phone numbers
    """
    business = request.user.business_set.first()
    if not business:
        return JsonResponse({'error': 'Business not found'}, status=400)
    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
        return JsonResponse({'error': 'Twilio credentials not found'}, status=400)
    
    # Check if Twilio credentials are set
    if not api_credential.twilioAccountSid or not api_credential.twilioAuthToken:
        return JsonResponse({'error': 'Twilio credentials not configured'}, status=400)
    
    # Get search parameters
    country = request.GET.get('country', 'US')
    area_code = request.GET.get('area_code', '')
    
    try:
        # Initialize Twilio client
        client = Client(api_credential.twilioAccountSid, api_credential.twilioAuthToken)
        
        # Search for available phone numbers
        search_params = {}
        if area_code:
            search_params['area_code'] = area_code
        
        # Limit to SMS capable numbers and ensure we get numbers that can receive SMS
        search_params['sms_enabled'] = True
        search_params['exclude_all_address_required'] = True  # Exclude numbers that require an address
        
      
        
        # Search for available phone numbers
        available_numbers = client.available_phone_numbers(country).local.list(**search_params)

        numbers = []
        for number in available_numbers:  
            numbers.append({
                'phone_number': number.phone_number,
                'friendly_name': number.friendly_name,
                'locality': getattr(number, 'locality', ''),
                'region': getattr(number, 'region', ''),
                'postal_code': getattr(number, 'postal_code', ''),
                'capabilities': {
                    'sms': getattr(number, 'capabilities', {}).get('SMS', False),
                    'voice': getattr(number, 'capabilities', {}).get('voice', False),
                    'mms': getattr(number, 'capabilities', {}).get('MMS', False),
                }
            })
        return JsonResponse({'numbers': numbers})
    
    except TwilioRestException as e:
        return JsonResponse({'error': f"Twilio error: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Error: {str(e)}"}, status=500)

@login_required
@require_POST
def purchase_twilio_number(request):
    """
    API endpoint to purchase a Twilio phone number
    """
    business = request.user.business_set.first()
    if not business:
        return JsonResponse({'error': 'Business not found'}, status=400)
    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
        return JsonResponse({'error': 'Twilio credentials not found'}, status=400)
    
    # Check if Twilio credentials are set
    if not api_credential.twilioAccountSid or not api_credential.twilioAuthToken:
        return JsonResponse({'error': 'Twilio credentials not configured'}, status=400)
    
    # Get the phone number to purchase
    data = json.loads(request.body)
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return JsonResponse({'error': 'Phone number is required'}, status=400)
    
    try:
        # Initialize Twilio client
        client = Client(api_credential.twilioAccountSid, api_credential.twilioAuthToken)
        
        # Generate webhook URL for SMS
        webhook_url = api_credential.getTwilioWebhookUrl()
        
        # Purchase the phone number
        purchased_number = client.incoming_phone_numbers.create(
            phone_number=phone_number,
            sms_url=webhook_url,
            sms_method='POST'
        )
        
        # Update the API credential with the new phone number
        api_credential.twilioSmsNumber = phone_number
        api_credential.save()
        
        return JsonResponse({
            'success': True,
            'phone_number': purchased_number.phone_number,
            'sid': purchased_number.sid
        })
    
    except TwilioRestException as e:
        return JsonResponse({'error': f"Twilio error: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Error: {str(e)}"}, status=500)

@login_required
def get_twilio_numbers(request):
    """
    API endpoint to get all Twilio phone numbers associated with the account
    """
    business = request.user.business_set.first()
    if not business:
        return JsonResponse({'error': 'Business not found'}, status=400)
    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
        return JsonResponse({'error': 'Twilio credentials not found'}, status=400)
    
    # Check if Twilio credentials are set
    if not api_credential.twilioAccountSid or not api_credential.twilioAuthToken:
        return JsonResponse({'error': 'Twilio credentials not configured'}, status=400)
    
    try:
        # Initialize Twilio client
        client = Client(api_credential.twilioAccountSid, api_credential.twilioAuthToken)
        
        # Get all phone numbers
        incoming_numbers = client.incoming_phone_numbers.list()
        
        # Format the results
        numbers = []
        for number in incoming_numbers:
            numbers.append({
                'phone_number': number.phone_number,
                'friendly_name': number.friendly_name,
                'sid': number.sid,
                'sms_url': number.sms_url,
                'sms_method': number.sms_method,
                'is_active': api_credential.twilioSmsNumber == number.phone_number
            })
        
        return JsonResponse({'numbers': numbers})
    
    except TwilioRestException as e:
      
        return JsonResponse({'error': f"Twilio error: {str(e)}"}, status=400)
    except Exception as e:
      
        return JsonResponse({'error': f"Error: {str(e)}"}, status=500)

@login_required
@require_POST
def update_twilio_webhook(request):
    """
    API endpoint to update the webhook URL for a Twilio phone number
    """
    business = request.user.business_set.first()
    if not business:
        return JsonResponse({'error': 'Business not found'}, status=400)
    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
        return JsonResponse({'error': 'Twilio credentials not found'}, status=400)
    
    # Check if Twilio credentials are set
    if not api_credential.twilioAccountSid or not api_credential.twilioAuthToken:
        return JsonResponse({'error': 'Twilio credentials not configured'}, status=400)
    
    # Get the phone number SID and webhook URL
    data = json.loads(request.body)
    phone_sid = data.get('phone_sid')
    
    if not phone_sid:
        return JsonResponse({'error': 'Phone SID is required'}, status=400)
    
    try:
        # Initialize Twilio client
        client = Client(api_credential.twilioAccountSid, api_credential.twilioAuthToken)
        
        # Generate webhook URL for SMS
        webhook_url = api_credential.getTwilioWebhookUrl()
        
        # Update the phone number's webhook URL
        updated_number = client.incoming_phone_numbers(phone_sid).update(
            sms_url=webhook_url,
            sms_method='POST'
        )
        
        return JsonResponse({
            'success': True,
            'phone_number': updated_number.phone_number,
            'sms_url': updated_number.sms_url
        })
    
    except TwilioRestException as e:
        return JsonResponse({'error': f"Twilio error: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Error: {str(e)}"}, status=500)

@login_required
@require_POST
def set_active_number(request):
    """
    API endpoint to set a phone number as the active SMS number
    """
    business = request.user.business_set.first()
    if not business:
        return JsonResponse({'error': 'Business not found'}, status=400)
    

    
    try:
        api_credential = ApiCredential.objects.get(business=business)
    except ApiCredential.DoesNotExist:
     
        return JsonResponse({'error': 'Twilio credentials not found'}, status=400)
    
    # Get the phone number to set as active
    data = json.loads(request.body)
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return JsonResponse({'error': 'Phone number is required'}, status=400)
    
    try:
        # Update the API credential with the new active phone number
        api_credential.twilioSmsNumber = phone_number
        api_credential.save()

        
        return JsonResponse({
            'success': True,
            'phone_number': phone_number
        })
    
    except Exception as e:
        print(e)
        return JsonResponse({'error': f"Error: {str(e)}"}, status=500)

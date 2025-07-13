from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt    
import requests
from django.db import transaction
from django.core.cache import cache
from asgiref.sync import sync_to_async
import json
import threading
from datetime import datetime, timedelta
from django.utils.timezone import make_aware, is_naive
import os

from rest_framework import status
from .models import *
from .api_views import get_cleaners_for_business, find_available_cleaner

from accounts.models import ApiCredential, Business, BusinessSettings, CustomAddons
from bookings.models import Booking, BookingCustomAddons
from .utils import calculateAmount, calculateAddonsAmount
from integrations.models import PlatformIntegration, DataMapping, IntegrationLog
from integrations.utils import log_integration_activity
from retell_agent.models import RetellAgent
from subscription.models import UsageTracker
from retell import Retell
from django.conf import settings
from openai import OpenAI

@csrf_exempt
def thumbtack_webhook(request, secretKey):
    """Handle incoming lead data from Thumbtack"""
    verifySecretKey = ApiCredential.objects.filter(secretKey=secretKey)
    if not verifySecretKey.exists():
        return JsonResponse({'message': 'Secret Key Not Verified'}, status=500)

    business = verifySecretKey.first().business

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print(f"Received Thumbtack webhook: {data}")
            
            # Extract required fields from the webhook payload
            lead_data = data.get('data', {})
            customer_data = lead_data.get('customer', {})
            request_data = lead_data.get('request', {})
            location_data = request_data.get('location', {})
            booking_data = request_data.get('booking', {})
            estimate_data = lead_data.get('estimate', {})
            
            # Process details from request data
            details_list = request_data.get('details', [])
            details_dict = {}
            
            # Extract questions and answers from details
            for detail in details_list:
                question = detail.get('question', '')
                answer = detail.get('answer', '')
                if question and answer:
                    details_dict[question] = answer
            
            # Create separate tracking for category information
            category = request_data.get('category', {})
            category_name = category.get('name', 'Unknown') if category else 'Unknown'
            
            # Create separate tracking for proposed times
            proposed_times = request_data.get('proposedTimes', [])
            proposed_start_datetime_str = proposed_times[0].get('start')
            proposed_end_datetime_str = proposed_times[0].get('end')
            
            # Extract proposed start and end datetime
            proposed_start = None
            proposed_end = None
            
            if proposed_start_datetime_str:
                try:
                    proposed_start = datetime.fromisoformat(proposed_start_datetime_str.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"Error parsing proposed start datetime: {e}")
            
            if proposed_end_datetime_str:
                try:
                    proposed_end = datetime.fromisoformat(proposed_end_datetime_str.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"Error parsing proposed end datetime: {e}")
            

            # Parse estimated price
            estimated_price = None
            if estimate_data.get('total'):
                try:
                    # Remove currency symbol and commas
                    price_str = estimate_data.get('total', '0')
                    # Handle both $1,234.56 and 1234.56 formats
                    price_str = price_str.replace('$', '').replace(',', '')
                    estimated_price = float(price_str)
                except ValueError:
                    estimated_price = None
            
            
            # Create formatted notes from important details
            notes = request_data.get('description', '')
            notes += f"Service: {category_name}\n"
            notes += f"Location: {location_data.get('city', 'N/A')}, {location_data.get('state', 'N/A')}\n"
            notes += f"Estimate: {estimate_data.get('total', 'N/A')}\n\n"
            
           
                
            # Add estimate details to notes
            if estimate_data:
                notes += "\nEstimate Details:\n"
                notes += f"- Type: {estimate_data.get('type', 'N/A')}\n"
                notes += f"- Total: {estimate_data.get('total', 'N/A')}\n"
                notes += f"- Price Per Unit: {estimate_data.get('pricePerUnit', 'N/A')}\n"
                notes += f"- Unit Quantity: {estimate_data.get('unitQuantity', 'N/A')}\n"
                notes += f"- Unit Name: {estimate_data.get('unitName', 'N/A')}\n"
            
            lead = Lead.objects.create(
                business=business,
                name=f"{customer_data.get('firstName', '')} {customer_data.get('lastName', '')}".strip(),
                email=customer_data.get('email', None),  # May be None
                phone_number=customer_data.get('Phone', ''),
                
                # Address fields
                address1=location_data.get('address1', ''),
                address2=location_data.get('address2', ''),
                city=location_data.get('city', ''),
                state=location_data.get('state', ''),
                zipCode=location_data.get('zipCode', ''),
                
                # Store only request details in the JSONField
                details=details_dict,
                
                # Store datetime information
                proposed_start_datetime=proposed_start,
                proposed_end_datetime=proposed_end,
                
                # Notes and source
                notes=notes,
                content=json.dumps(data, indent=2),  # Store raw JSON as content
                source="Thumbtack",
                
                
                # Pricing
                estimatedPrice=estimated_price
            )
            
            print(f"Successfully created Thumbtack lead: {lead.leadId}")
            
            # Track usage
            try:
                from subscription.models import UsageTracker
                UsageTracker.increment_leads(business=business, increment_by=1)
            except Exception as e:
                print(f"Error tracking lead usage: {e}")
                
            return JsonResponse({'status': 'success', 'lead_id': lead.leadId}, status=200)
            
        except Exception as e:
            print(f"Error processing Thumbtack webhook: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return JsonResponse({'message': f'Error: {str(e)}'}, status=500)
    
    return JsonResponse({'status': 'success'}, status=200)




@csrf_exempt
def handle_retell_webhook(request, secretKey):
    """Handle incoming Retell webhook requests"""
    if request.method != 'POST':
        return HttpResponse(status=405)
        
    try:
        if not request.body:
            return HttpResponse(status=400)
        
        # Quick validation of credentials
        apiCredentialObj = ApiCredential.objects.filter(secretKey=secretKey).first()
        if not apiCredentialObj:
            return HttpResponse(status=401)  # Unauthorized
            
        # Parse and validate basic request structure
        post_data = json.loads(request.body)
        event = post_data.get("event")
        if not event:
            return HttpResponse(status=400)
            
        # Start processing in a background thread
        webhook_data = {
            "post_data": post_data,
            "api_credential_id": apiCredentialObj.id
        }
        thread = threading.Thread(target=process_webhook_data, args=(webhook_data,))
        thread.start()
        
        # Return immediate success response
        return HttpResponse(status=200)

    except json.JSONDecodeError:
        return HttpResponse(status=400)
    except Exception as e:
        return HttpResponse(status=500)

@transaction.atomic
def process_webhook_data(webhook_data):
    """Process webhook data in a background thread"""
    try:
        post_data = webhook_data["post_data"]
        api_credential_id = webhook_data["api_credential_id"]

        print(f"Processing webhook data: {post_data}")
        
        # Get API credentials and business
        apiCredentialObj = ApiCredential.objects.get(id=api_credential_id)
        businessObj = apiCredentialObj.business
        
        event = post_data.get("event")
        call_data = post_data.get("call", {})
        call_id = call_data.get("call_id") or call_data.get("id", "")
      
        if event == 'call_ended':
            print(f"Call ended: {call_id}")
            
            # Get timestamps directly from the webhook payload
            start_timestamp = call_data.get("start_timestamp")
            end_timestamp = call_data.get("end_timestamp")
            
            if start_timestamp and end_timestamp:
                # Convert milliseconds to seconds and make timezone-aware
                start_time = make_aware(datetime.fromtimestamp(start_timestamp / 1000))
                end_time = make_aware(datetime.fromtimestamp(end_timestamp / 1000))
                
                # Calculate duration in minutes
                duration = end_time - start_time
                minutes = max(1, round(duration.total_seconds() / 60))
                
                # Track usage
                UsageTracker.increment_minutes(businessObj, minutes)
                print(f"Call {call_id} lasted {minutes} minutes")
                
                # Log the details for debugging
                print(f"Start time: {start_time}, End time: {end_time}, Duration: {duration}")
            else:
                # Fallback to a default value if timestamps are missing
                UsageTracker.increment_minutes(businessObj, 1)
                print(f"Used fallback duration of 1 minute for call {call_id} (missing timestamps)")
    
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        import traceback
        print(traceback.format_exc())



# Sending Data to External Sources
def create_mapped_payload(booking_data, integration):
    """Create payload based on user-defined field mappings"""
    mappings = DataMapping.objects.filter(platform=integration)
    payload = {}
    
    # Convert datetime fields to string format
    if isinstance(booking_data["cleaningDate"], datetime):
        booking_data = dict(booking_data)  # Create a copy to avoid modifying the original
        booking_data["cleaningDate"] = booking_data["cleaningDate"].date().isoformat()
        # Store the datetime object before converting to string
        start_time_dt = booking_data["startTime"]
        # Calculate end time using the datetime object
        end_time_dt = start_time_dt + timedelta(minutes=60)
        # Convert to string format after calculations
        booking_data["startTime"] = start_time_dt.strftime("%H:%M:%S")
        booking_data["endTime"] = end_time_dt.strftime("%H:%M:%S")

    # Apply mappings
    for mapping in mappings:
        source_value = booking_data.get(mapping.source_field)
        
        # Skip if source field doesn't exist
        if source_value is None and not mapping.default_value:
            if mapping.is_required:
                raise ValueError(f"Required field {mapping.source_field} not found in booking data")
            continue
            
        # Use default value if source is None
        if source_value is None:
            source_value = mapping.default_value
                
        # Handle nested fields
        if mapping.parent_path:
            parts = mapping.parent_path.split('.')
            current = payload
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            if parts[-1] not in current:
                current[parts[-1]] = {}
            current[parts[-1]][mapping.target_field] = source_value
        else:
            payload[mapping.target_field] = source_value
            
    return payload



@csrf_exempt
def chatgpt_analysis_webhook(request, secretKey):
    """Handle incoming JSON data, analyze it with ChatGPT, and store structured response in Lead model"""
    # Verify secret key
    verifySecretKey = ApiCredential.objects.filter(secretKey=secretKey)
    if not verifySecretKey.exists():
        return JsonResponse({'message': 'Secret Key Not Verified'}, status=401)

    business = verifySecretKey.first().business

    if request.method == 'POST':
        try:
            # Parse incoming JSON data
            data = json.loads(request.body)
            print(f"Received data for ChatGPT analysis: {data}")
            
            # Initialize OpenAI client
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            
            # Define the system prompt for analysis
            system_prompt = """
            You are a data extraction assistant. Your task is to analyze the provided JSON data 
            and extract structured information for a cleaning service lead. Extract the following fields 
            if available (leave blank if not found):
            
            1. name: Full name of the customer
            2. email: Customer's email address
            3. phone_number: Customer's phone number
            4. bedrooms: Number of bedrooms (numeric)
            5. bathrooms: Number of bathrooms (numeric)
            6. squareFeet: Size of the property in square feet (numeric)
            7. type_of_cleaning: Type of cleaning service requested
            8. address1: Street address
            9. address2: Apartment/unit number or additional address info
            10. city: City name
            11. state: State name
            12. zipCode: ZIP/Postal code
            13. proposed_start_datetime: Proposed start date and time (ISO format if possible)
            14. proposed_end_datetime: Proposed end date and time (ISO format if possible)
            15. estimatedPrice: Estimated price for the service (numeric)
            16. notes: Any additional notes or special requests
            17. source: Source of the lead (if available, otherwise use "API")
            
            Return ONLY a JSON object with these fields. Do not include any explanations or additional text.
            """
            
            # Call ChatGPT API to analyze the data
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this data: {json.dumps(data)}"}
                ],
                response_format={"type": "json_object"}
            )
            
            # Parse the structured response
            structured_data = json.loads(response.choices[0].message.content)
            print(f"Structured data from ChatGPT: {structured_data}")
            
            # Extract fields for Lead model
            lead_data = {
                'business': business,
                'name': structured_data.get('name', ''),
                'email': structured_data.get('email'),
                'phone_number': structured_data.get('phone_number', ''),
                'bedrooms': structured_data.get('bedrooms'),
                'bathrooms': structured_data.get('bathrooms'),
                'squareFeet': structured_data.get('squareFeet'),
                'type_of_cleaning': structured_data.get('type_of_cleaning'),
                'address1': structured_data.get('address1'),
                'address2': structured_data.get('address2'),
                'city': structured_data.get('city'),
                'state': structured_data.get('state'),
                'zipCode': structured_data.get('zipCode'),
                'estimatedPrice': structured_data.get('estimatedPrice'),
                'notes': structured_data.get('notes'),
                'content': json.dumps(data, indent=2),  # Store original JSON
                'source': structured_data.get('source', 'API'),
                'details': data  # Store full original data in details field
            }
            
            # Handle datetime fields if present
            proposed_start = structured_data.get('proposed_start_datetime')
            if proposed_start:
                try:
                    lead_data['proposed_start_datetime'] = datetime.fromisoformat(proposed_start.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"Error parsing proposed start datetime: {e}")
            
            proposed_end = structured_data.get('proposed_end_datetime')
            if proposed_end:
                try:
                    lead_data['proposed_end_datetime'] = datetime.fromisoformat(proposed_end.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"Error parsing proposed end datetime: {e}")
            
            # Create the Lead object
            lead = Lead.objects.create(**lead_data)
            print(f"Successfully created lead from ChatGPT analysis: {lead.leadId}")
            
            # Track usage
            try:
                UsageTracker.increment_leads(business=business, increment_by=1)
            except Exception as e:
                print(f"Error tracking lead usage: {e}")
                
            return JsonResponse({
                'status': 'success', 
                'lead_id': lead.leadId,
                'structured_data': structured_data
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({'message': 'Invalid JSON data'}, status=400)
        except Exception as e:
            print(f"Error processing ChatGPT analysis webhook: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return JsonResponse({'message': f'Error: {str(e)}'}, status=500)
    
    return JsonResponse({'message': 'Method not allowed'}, status=405)


def send_booking_data(booking):
    """Send booking data to integration webhook"""
    try:
        # Get all active integrations for the business
        integrations = PlatformIntegration.objects.filter(
            business=booking.business,
            is_active=True
        )
        
        if not integrations.exists():
            print(f"No active integrations found for business {booking.business.businessName}")
            return

        results = {
            'workflow': {'success': [], 'failed': []},
            'direct_api': {'success': [], 'failed': []}
        }
        
        print(f"Processing {integrations.count()} integrations for business {booking.business.businessName}")
        
        for integration in integrations:
            try:
                integration_type = 'workflow' if integration.platform_type == 'workflow' else 'direct_api'
                print(f"Processing {integration_type} integration: {integration.name}")
                
                if integration.platform_type == 'workflow':
                    # For workflow platforms, use the default payload structure
                    payload = {
                        "firstName": booking.firstName,
                        "lastName": booking.lastName,
                        "email": booking.email,
                        "phoneNumber": booking.phoneNumber,
                        "address1": booking.address1,
                        "address2": booking.address2,
                        "city": booking.city,
                        "stateOrProvince": booking.stateOrProvince,
                        "zipCode": booking.zipCode,
                        "bedrooms": booking.bedrooms,
                        "bathrooms": booking.bathrooms,
                        "squareFeet": booking.squareFeet,
                        "serviceType": booking.serviceType,
                        "cleaningDate": booking.cleaningDate.strftime('%Y-%m-%d') if booking.cleaningDate else None,
                        "startTime": booking.startTime.strftime('%H:%M') if booking.startTime else None,
                        "endTime": booking.endTime.strftime('%H:%M') if booking.endTime else None,
                        "totalPrice": float(booking.totalPrice),
                        "tax": float(booking.tax or 0),
                        "addonDishes": booking.addonDishes,
                        "addonLaundryLoads": booking.addonLaundryLoads,
                        "addonWindowCleaning": booking.addonWindowCleaning,
                        "addonPetsCleaning": booking.addonPetsCleaning,
                        "addonFridgeCleaning": booking.addonFridgeCleaning,
                        "addonOvenCleaning": booking.addonOvenCleaning,
                        "addonBaseboard": booking.addonBaseboard,
                        "addonBlinds": booking.addonBlinds,
                        "addonGreenCleaning": booking.addonGreenCleaning,
                        "addonCabinetsCleaning": booking.addonCabinetsCleaning,
                        "addonPatioSweeping": booking.addonPatioSweeping,
                        "addonGarageSweeping": booking.addonGarageSweeping
                    }
                    
                    print(f"Sending data to workflow webhook: {integration.webhook_url}")
                    # Prepare headers
                    headers = {"Content-Type": "application/json"}
                    
                    # Add custom headers from integration if available
                    if integration.headers:
                        headers.update(integration.headers)
                    
                    # Send to webhook URL
                    response = requests.post(
                        integration.webhook_url,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )

                    # Log successful integration
                    if response.status_code in [200, 201]:
                        log_integration_activity(
                            platform=integration,
                            status='success',
                            request_data=payload,
                            response_data=response.json() if response.text else None
                        )
                    
                    # Log failed integration
                    else:
                        log_integration_activity(
                            platform=integration,
                            status='failed',
                            request_data=payload,
                            error_message=response.text
                        )
                    
                else:  # direct_api
                    # Create payload using field mappings
                    print(f"Creating mapped payload for {integration.name}")
                    # Convert date fields to string format before creating mapped payload
                    booking_dict = booking.__dict__.copy()
                    if 'cleaningDate' in booking_dict:
                        booking_dict['cleaningDate'] = booking.cleaningDate.strftime('%Y-%m-%d') if booking.cleaningDate else None
                    if 'startTime' in booking_dict:
                        booking_dict['startTime'] = booking.startTime.strftime('%H:%M') if booking.startTime else None
                    if 'endTime' in booking_dict:
                        booking_dict['endTime'] = booking.endTime.strftime('%H:%M') if booking.endTime else None
                    
                    payload = create_mapped_payload(booking_dict, integration)
                    
                    # Send to base URL
                    headers = {"Content-Type": "application/json"}
                    
                   
                    
                    # Add custom headers from integration if available
                    if integration.headers:
                        headers.update(integration.headers)
                    
                    print(f"Sending data to API endpoint: {integration.base_url}")
                    response = requests.post(
                        integration.base_url,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                
                    # Log successful integration
                    if response.status_code in [200, 201]:
                        log_integration_activity(
                            platform=integration,
                            status='success',
                            request_data=payload,
                            response_data=response.json() if response.text else None
                        )
                    
                    # Log failed integration
                    else:
                        log_integration_activity(
                            platform=integration,
                            status='failed',
                            request_data=payload,
                            error_message=response.text
                        )
                    
                
                results[integration_type]['success'].append({
                    'name': integration.name,
                    'response': response.text,
                    'status_code': response.status_code
                })
                
            except Exception as e:
                error_msg = f"Error sending booking data to {integration.name}: {str(e)}"
                print(error_msg)
                
                # Log failed integration
                log_integration_activity(
                    platform=integration,
                    status='failed',
                    request_data=payload if 'payload' in locals() else {},
                    error_message=str(e)
                )
                
                results[integration_type]['failed'].append({
                    'name': integration.name,
                    'error': str(e)
                })
                continue

        # Print summary
        print("\nIntegration Summary:")
        for int_type in ['workflow', 'direct_api']:
            print(f"\n{int_type.upper()} Integrations:")
            print(f"Success: {len(results[int_type]['success'])} integration(s)")
            print(f"Failed: {len(results[int_type]['failed'])} integration(s)")
            
            if results[int_type]['failed']:
                print("\nFailed integrations:")
                for fail in results[int_type]['failed']:
                    print(f"- {fail['name']}: {fail['error']}")

        return results

    except Exception as e:
        print(f"Error in send_booking_data: {str(e)}")
        raise Exception(f"Error in send_booking_data: {str(e)}")

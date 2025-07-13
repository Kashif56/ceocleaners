from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from datetime import datetime

from accounts.models import Business, ApiCredential
from .models import AgentConfiguration, Chat, Messages
from automation.models import Lead
from bookings.models import Booking

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.messaging_response import MessagingResponse
from .openai_agent import OpenAIAgent
import os
import traceback
from openai import OpenAI
import threading
from twilio.rest import Client
import json

# Create your views here.

@login_required
def all_chats(request):
    """
    View all chats for the current user's business
    """
    try:
        # Get the current user's business
        business = Business.objects.filter(user=request.user).first()
        
        if not business:
            messages.error(request, "You need to have a business registered to view chats.")
            return redirect('home')
        
        # Get all chats for this business
        chats = Chat.objects.filter(business=business).order_by('-updatedAt')
        
        # Get the last message for each chat
        for chat in chats:
            # Filter out tool messages when finding the last message
            last_message = Messages.objects.filter(chat=chat).exclude(role='tool').order_by('-createdAt').first()
            
            # If no non-tool message found, check if there's any message at all
            if not last_message:
                last_message = Messages.objects.filter(chat=chat).order_by('-createdAt').first()
            
            chat.last_message = last_message.message if last_message else "No messages"
            chat.last_message_time = last_message.createdAt if last_message else chat.createdAt
            
            # Get lead name if available
            lead = Lead.objects.filter(phone_number=chat.clientPhoneNumber).first()
            chat.lead_name = lead.name if lead else chat.clientPhoneNumber or f"WebChat: {chat.sessionKey}"
        
        # Get business timezone for template use
        business_timezone = business.get_timezone()
        
        return render(request, 'ai_agent/all_chats.html', {
            'chats': chats,
            'business': business,
            'user_timezone': business_timezone  # Pass timezone to template
        })
        
    except Exception as e:
        print(f"[VIEW] Error in all_chats view: {str(e)}")
        print(traceback.format_exc())
        messages.error(request, "An error occurred while retrieving chats.")
        return redirect('home')


@login_required
@require_POST
def delete_chat(request):
    """
    Endpoint to delete a chat (works with both AJAX and regular form submissions)
    """
    try:
        # Check if it's JSON data
        if request.headers.get('content-type') == 'application/json':
            try:
                data = json.loads(request.body)
                chat_id = data.get('chat_id')
            except json.JSONDecodeError:
                chat_id = None
        else:
            # Handle form data
            chat_id = request.POST.get('chat_id')
        
        if not chat_id:
            # Return JSON response for AJAX requests
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Chat ID is required'})
            # Return redirect with message for regular form submissions
            messages.error(request, "Chat ID is required")
            return redirect('ai_agent:all_chats')
        
        # Get the current user's business
        business = Business.objects.filter(user=request.user).first()
        
        if not business:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'No business found for this user'})
            messages.error(request, "No business found for this user")
            return redirect('ai_agent:all_chats')
        
        # Get the chat
        try:
            chat = Chat.objects.get(id=chat_id, business=business)
        except Chat.DoesNotExist:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Chat not found'})
            messages.error(request, "Chat not found")
            return redirect('ai_agent:all_chats')
        
        # Delete all messages first (CASCADE should handle this, but being explicit)
        Messages.objects.filter(chat=chat).delete()
        
        # Delete the chat
        chat.delete()
        
        # Return appropriate response
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Chat deleted successfully'})
        
        messages.success(request, "Chat deleted successfully")
        return redirect('ai_agent:all_chats')
        
    except Exception as e:
        print(f"[VIEW] Error in delete_chat: {str(e)}")
        print(traceback.format_exc())
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': f"Error: {str(e)}"})
        
        messages.error(request, f"Error deleting chat: {str(e)}")
        return redirect('ai_agent:all_chats')

@login_required
@require_POST
def agent_config_delete(request):
    """View to delete an agent configuration"""
    business = get_object_or_404(Business, user=request.user)
    
    # Get the configuration for this business
    config = AgentConfiguration.objects.filter(business=business).first()
    
    if config:
        business_name = business.businessName
        config.delete()
        messages.success(request, f"Configuration for {business_name} deleted successfully.")
    else:
        messages.warning(request, "No configuration found to delete.")
    
    return redirect('ai_agent:agent_config')


@login_required
def agent_config_unified(request):
    """Unified view to create or edit agent configuration on a single page"""
    from .utils import default_prompt
    business = Business.objects.filter(user=request.user).first()
    
    if not business:
        messages.error(request, "You need to have a business registered before configuring the AI Agent.")
        return redirect('home')
    
    # Get or create configuration for this business
    config, created = AgentConfiguration.objects.get_or_create(
        business=business,
        defaults={
            'prompt': '',
            'agent_name': 'Sarah'
        }
    )

    if created:
        prompt = default_prompt(business)
        if prompt != None:
            config.prompt = prompt
            config.save()
    
    if request.method == 'POST':
        # Update configuration
        config.prompt = request.POST.get('prompt', config.prompt)
        config.agent_name = request.POST.get('agent_name', config.agent_name)
        config.save()
        
        messages.success(request, f"Configuration for {business.businessName} updated successfully.")
        
        # Generate the system prompt for preview
        system_prompt = OpenAIAgent.get_dynamic_system_prompt(business.businessId)
        
        return render(request, 'ai_agent/agent_config_unified.html', {
            'config': config,
            'business': business,
            'system_prompt': system_prompt,
            'show_preview': True
        })
    
    return render(request, 'ai_agent/agent_config_unified.html', {
        'config': config,
        'business': business,
        'created': created
    })

@login_required
def agent_config_save(request):
    """AJAX view to save agent configuration"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    
    business = Business.objects.filter(user=request.user).first()
    if not business:
        return JsonResponse({'success': False, 'message': 'No business found for this user'})
    
    
    config = AgentConfiguration.objects.get(business=business)
    
    # Update configuration
    config.prompt = request.POST.get('prompt', config.prompt)
    
    # Update agent name if provided
    agent_name = request.POST.get('agent_name')
    if agent_name:
        config.agent_name = agent_name
    
    config.save()
    
    # Generate the system prompt for preview
    system_prompt = OpenAIAgent.get_dynamic_system_prompt(business.businessId)
    
    return JsonResponse({
        'success': True, 
        'message': f"Configuration for {business.businessName} updated successfully.",
        'system_prompt': system_prompt
    })


@login_required
def embed_agent(request):
    """View for embedding AI Agent on external websites"""
    business = Business.objects.filter(user=request.user).first()
    
    if not business:
        messages.error(request, "You need to have a business registered before configuring the AI Agent.")
        return redirect('home')
    
    # Get configuration for this business
    config = AgentConfiguration.objects.filter(business=business).first()
    
    return render(request, 'ai_agent/embed_agent.html', {
        'config': config,
        'business': business
    })
        
  


# AI AGENT START


@csrf_exempt
def twilio_webhook(request, secretKey):
    """Handle Twilio webhook requests for SMS interactions"""
    # Check if this is a POST request
    if request.method != 'POST':
        print("[DEBUG] Method not allowed - not a POST request")
        return HttpResponse('Method not allowed', status=405)
    
    # Get the incoming SMS data
    from_number = request.POST.get('From', '')
    body = request.POST.get('Body', '')
    to_number = request.POST.get('To', '')

    from usage_analytics.services.usage_service import UsageService
    apiCred = ApiCredential.objects.filter(secretKey=secretKey).first()
    business = apiCred.business
    check_limit = UsageService.check_sms_messages_limit(business)
    if check_limit.get('exceeded'):
        print("SMS Limit reached for your Plan")
        return JsonResponse({
            'error': 'SMS limit exceeded'
        }, status=400)

    print(f"[DEBUG] SMS received - From: {from_number}, To: {to_number}")
    print(f"[DEBUG] Message body: {body}")
    
    # Initialize Twilio response
    twiml_response = MessagingResponse()
    
    try:
        # Immediately acknowledge receipt to avoid Twilio timeout
        # Start processing in background thread without sending an acknowledgment message
        print("[DEBUG] Starting background thread for async processing")
        threading.Thread(
            target=process_sms_async,
            args=(secretKey, from_number, body, to_number),
            daemon=True
        ).start()
        
        # Return an empty TwiML response to acknowledge the webhook without sending a message
        print("[DEBUG] Returning empty TwiML response to Twilio")
        return HttpResponse(str(twiml_response), content_type='text/xml')
        
    except Exception as e:
        print(f"[DEBUG] Error in Twilio webhook: {str(e)}")
        traceback.print_exc()
        
        # Send a generic error message
        print("[DEBUG] Sending error message to user")
        twiml_response.message("Sorry, we encountered an error processing your request. Please try again later.")
        return HttpResponse(str(twiml_response), content_type='text/xml')

def process_sms_async(secretKey, from_number, body, to_number):
    """Process SMS message asynchronously and send response when ready"""
    print(f"\n[DEBUG] Starting async processing for {from_number}")
    print(f"[DEBUG] Async process timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        # Clean the phone number (remove any + prefix)
        client_phone_number = from_number
        
        print(f"[DEBUG] Using client phone number: {client_phone_number}")
        
        print(f"[DEBUG] Fetching API credentials with secretKey: {secretKey}")
        apiCred = ApiCredential.objects.filter(secretKey=secretKey).first()
        
        if not apiCred:
            print("[DEBUG] API credentials not found")
            send_sms_response(from_number, "Sorry, we couldn't process your request at this time.", apiCred)
            return
        
        business = apiCred.business
        print(f"[DEBUG] Business found: {business.businessName} (ID: {business.businessId})")
        
        # Get or create a chat for this phone number
        print(f"[DEBUG] Getting or creating chat for business ID {business.businessId} and phone {client_phone_number}")
        chat = OpenAIAgent.get_or_create_chat(business.businessId, client_phone_number, session_key=None)
        
        if not chat:
            print("[DEBUG] Failed to get or create chat")
            send_sms_response(from_number, "Sorry, we couldn't process your request at this time.", apiCred)
            return
        
        print(f"[DEBUG] Chat retrieved/created successfully (ID: {chat.id})")
        
        # Save user message
        print("[DEBUG] Saving user message to database")
        user_message = Messages.objects.create(
            chat=chat,
            role='user',
            message=body
        )
        print(f"[DEBUG] User message saved (ID: {user_message.id})")
        
        # Get the system prompt
        print("[DEBUG] Retrieving dynamic system prompt")
        system_prompt = OpenAIAgent.get_dynamic_system_prompt(business.businessId)
      
        
        # Get all messages for this chat
        print("[DEBUG] Retrieving chat history")
        messages = OpenAIAgent.get_chat_messages(client_phone_number, session_key=None)
        print(f"[DEBUG] Retrieved {len(messages)} messages from chat history")
        
        # Format messages for OpenAI
        print("[DEBUG] Formatting messages for OpenAI API")
        formatted_messages = OpenAIAgent.format_messages_for_openai(messages, system_prompt)
        
        # Call OpenAI API
        print("[DEBUG] Initializing OpenAI client")
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        try:
            print("[DEBUG] Calling OpenAI API")
            print(f"[DEBUG] API call timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=formatted_messages,
                temperature=0.5,
                max_tokens=3000, 
                tools=OpenAIAgent.get_openai_tools()
            )
            print(f"[DEBUG] OpenAI API response received at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Process the response
            print("[DEBUG] Processing AI response")
            ai_response_text = OpenAIAgent.process_ai_response(response, client_phone_number, business, None)
            ai_response = ai_response_text.get('content')
            # Save the assistant message
            print("[DEBUG] Saving assistant message to database")
            assistant_message = Messages.objects.create(
                chat=chat,
                role='assistant',
                message=ai_response
            )
            print(f"[DEBUG] Assistant message saved (ID: {assistant_message.id})")
            
            # Send the AI response back via SMS
            # Truncate if necessary to fit SMS length limits
            original_length = len(ai_response)
            if len(ai_response) > 1500:
                print(f"[DEBUG] Truncating response from {original_length} to 1500 characters")
                ai_response = ai_response[:1497] + "..."
            
            print("[DEBUG] Sending final response to user")
            send_sms_response(from_number, ai_response, apiCred)
            print(f"[DEBUG] Async processing completed for {from_number} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            print(f"[DEBUG] Error calling OpenAI API: {str(e)}")
            traceback.print_exc()
            send_sms_response(from_number, "Sorry, we're experiencing technical difficulties. Please try again later.", apiCred)
        
    except Exception as e:
        print(f"[DEBUG] Error in async SMS processing: {str(e)}")
        traceback.print_exc()
        send_sms_response(from_number, "Sorry, we encountered an error processing your request. Please try again later.", apiCred)


def send_sms_response(to_number, message, apiCred):
    """Send SMS response using Twilio client"""
    print(f"\n[DEBUG] Preparing to send SMS to {to_number}")
    print(f"[DEBUG] SMS sending timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        print("[DEBUG] Initializing Twilio client")
        account_sid = apiCred.twilioAccountSid
        auth_token = apiCred.twilioAuthToken
        from_number = apiCred.twilioSmsNumber
        business = apiCred.business
        
        # Check if credentials are available
        if not account_sid or not auth_token or not from_number:
            print(f"[DEBUG] Missing Twilio credentials - SID: {account_sid is not None}, Auth: {auth_token is not None}, From: {from_number}")
            return
        
        # Safely log partial credentials
        sid_display = f"{account_sid[:4]}...{account_sid[-4:]}" if account_sid and len(account_sid) > 8 else "[MISSING]"
        print(f"[DEBUG] Using Twilio credentials - SID: {sid_display} From: {from_number}")
        
        client = Client(account_sid, auth_token)
        
        # Send message
        print(f"[DEBUG] Sending message (length: {len(message)})")
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        from .utils import get_chat_status, find_by_phone_number
        from subscription.models import UsageTracker
        from automation.models import Lead
        
        print(f"[DEBUG] Finding chat for phone number: {to_number}")
        
        # Find chat with reusable function
        chat = find_by_phone_number(Chat, 'clientPhoneNumber', to_number, business)
        if chat:
            print(f"[DEBUG] Chat found: {chat}")
            get_chat_status(chat)

            
        # Find lead with the same function
        lead = find_by_phone_number(Lead, 'phone_number', to_number, business)
        
        print(f"[DEBUG] Lead found: {lead}")
        if lead:
            lead.is_response_received = True
            lead.save()
        
        print(f"[DEBUG] SMS sent successfully. Twilio SID: {message_obj.sid}")
    except Exception as e:
        print(f"[DEBUG] Error sending SMS response: {str(e)}")
        traceback.print_exc()


@login_required
def business_credentials_api(request):
    """
    API endpoint to get business credentials for the current user's business
    
    Args:
        request: Django request object
        
    Returns:
        JsonResponse with the business credentials
    """
    try:
        # Get the current user's business
        business = Business.objects.get(user=request.user)
        
        # Get the API credentials for the business
        try:
            credentials = ApiCredential.objects.get(business=business)
            return JsonResponse({
                'success': True,
                'credentials': {
                    'twilioSmsNumber': credentials.twilioSmsNumber,
                }
            })
        except ApiCredential.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'No API credentials found for this business'
            })
            
    except Business.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No business found for this user'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@require_http_methods(["GET"])
def get_chat_data(request, chat_id):
    try:
        # Get the business for the current user
        business = Business.objects.filter(user=request.user).first()
        if not business:
            return JsonResponse({
                'success': False,
                'message': 'No business found for this user'
            }, status=403)
            
        # Get the chat and make sure it belongs to this business
        print(f"[DEBUG] Getting chat data for chat ID: {chat_id}")
        chat = get_object_or_404(Chat, id=chat_id, business=business)
        
        # Get messages
        messages = Messages.objects.filter(chat=chat).order_by('createdAt')
        
        # Get lead information
        lead = Lead.objects.filter(phone_number=chat.clientPhoneNumber).first()
        lead_name = lead.name if lead else "Unknown"

        # Get booking details if available
        booking_details = None
        booking_id = chat.summary.get('bookingId') if chat.summary else None
        
        if booking_id:
            booking = Booking.objects.filter(bookingId=booking_id).first()
            if booking:
                # Create the booking details dictionary
                booking_details = {
                    'bookingId': booking.bookingId,
                    'firstName': booking.firstName,
                    'lastName': booking.lastName,
                    'phoneNumber': booking.phoneNumber,
                    'email': booking.email,
                    'address1': booking.address1,
                    'city': booking.city,
                    'stateOrProvince': booking.stateOrProvince,
                    'zipCode': booking.zipCode,
                    'cleaningDate': booking.cleaningDate.strftime('%Y-%m-%d') if booking.cleaningDate else None,
                    'startTime': booking.startTime.strftime('%H:%M') if booking.startTime else None,
                    'endTime': booking.endTime.strftime('%H:%M') if booking.endTime else None,
                    'serviceType': booking.serviceType,
                    'recurring': booking.recurring,
                    'totalPrice': float(booking.totalPrice) if booking.totalPrice else 0,
                    'isCompleted': booking.isCompleted,
                    'cleaner': booking.cleaner.name if booking.cleaner else None,
                    'bedrooms': booking.bedrooms,
                    'bathrooms': booking.bathrooms,
                    'squareFeet': booking.squareFeet,
                    'otherRequests': booking.otherRequests
                }
                
                # Add addon services from chat.summary to booking_details
                if chat.summary:
                    # Find all addon keys in the summary
                    addon_services = {}
                    for key, value in chat.summary.items():
                        if key.startswith('addon') and (value is True or value == "true" or value == "yes" or value == "Yes"):
                            addon_services[key] = value
                    
                    # Add addons to booking_details
                    if addon_services:
                        booking_details['addon_services'] = addon_services
                        booking_details['has_addons'] = True
                    else:
                        booking_details['has_addons'] = False
        
        messages_data = [{
            'role': msg.role,
            'message': msg.message,
            'createdAt': msg.createdAt.isoformat()
        } for msg in messages]
        
        return JsonResponse({
            'success': True,
            'lead_name': lead_name,
            'phone_number': chat.clientPhoneNumber,
            'status': chat.status,
            'messages': messages_data,
            'summary': chat.summary,
            'booking_details': booking_details
        })
    except Exception as e:
        print(f"Error in get_chat_data: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

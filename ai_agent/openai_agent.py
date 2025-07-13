from dotenv import load_dotenv
import os
import json
from datetime import datetime, timedelta
import pytz
import traceback
from openai import OpenAI

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from accounts.models import Business, CustomAddons
from bookings.models import Booking
from .models import Chat, Messages, AgentConfiguration
from .api_views import check_availability, book_appointment, get_current_time_in_chicago, calculate_total, reschedule_appointment, cancel_appointment
from .utils import convert_date_str_to_date
import re

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Define available tools
tools = {
    'check_availability': check_availability,
    'bookAppointment': book_appointment,
    'current_time': get_current_time_in_chicago,
    'calculateTotal': calculate_total,
    'reschedule_appointment': reschedule_appointment,
    'cancel_appointment': cancel_appointment
}

# Define OpenAI tools schema
openai_tools = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check if a specific date and time is available for booking",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "The date and time to check availability for (e.g., 'Tomorrow at 2 PM', 'March 15, 2025 at 10 AM')"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bookAppointment",
            "description": "Book an appointment after collecting all required customer information",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Get the current time in Chicago timezone",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculateTotal",
            "description": "Calculate the total cost of the appointment",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Reschedule an existing appointment to a new date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID of the appointment to reschedule"
                    },
                    "new_date_time": {
                        "type": "string",
                        "description": "The new date and time for the appointment (e.g., 'Tomorrow at 2 PM', 'March 15, 2025 at 10 AM')"
                    }
                },
                "required": ["booking_id", "new_date_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID of the appointment to cancel"
                    }
                },
                "required": ["booking_id"]
            }
        }
    }
]

class OpenAIAgent:
    """Class to handle OpenAI agent functionality with improved organization and error handling"""
    
    @staticmethod
    def get_dynamic_system_prompt(business_id):
        """Generate a dynamic system prompt based on the business and agent configuration
        stored in the database. Falls back to default prompt if no configuration exists.
        
        Args:
            business_id: The ID of the business to generate the prompt for
            
        Returns:
            String containing the system prompt, or 0 if no configuration exists
        """
        try:
            # Get the business object
            business = Business.objects.get(businessId=business_id)
            
            # Try to get agent configuration for this business
            try:
                agent_config = AgentConfiguration.objects.get(business=business)
                
                system_prompt = f"""You are {agent_config.agent_name}, virtual customer support and sales representative. You are speaking with a potential customer.
                  
                    ALWAYS ASK ONE QUESTION AT A TIME.

                    ##PRIMARY ROLE AND KNOWLEDGE SOURCE
                    Your primary role is to answer questions about cleaning services using ONLY the information provided by the business. DO NOT make up information or use general knowledge about cleaning that hasn't been explicitly provided by {business.businessName}.
                    You are also responsible for booking appointments for the customer.
                    You are responsible for collecting all required customer information and booking the appointment.
                    You are responsible for calculating the total cost of the appointment.
                    You are responsible for confirming the appointment with the customer.
                    Ideally you will be provided with leads details and you will be able to use that information to book the appointment.
                    If you have leads details, confirm the details with the customer on each step of the booking process respectively.
                    Like if you have Customer Name, and Phone Number When You rached step for Customer Name, you will confirm the name with the customer. Like "Is this correct? Name: [Customer Name] and Phone Number: [Phone Number]"
                    If you have Customer Address, and Customer City, State, Zip Code, When You rached step for Customer Address, you will confirm the address with the customer. Like "Is this correct? Address: [Customer Address], City: [Customer City], State: [Customer State], Zip Code: [Customer Zip Code]"
                    If you have Proposed Start Time, When You reached step for getting preferred date time, you will confirm the time with the customer. Like "I have your preferred date and time as [Proposed Start Time], is this correct?"
    
                    ##BOOKING STATUS AWARENESS - VERY IMPORTANT
                    1. Carefully track if a booking has already been completed in the conversation.
                    2. If a booking has been confirmed (booking ID exists or tool call was successful), DO NOT attempt to book again unless the customer EXPLICITLY asks for another/additional booking.
                    3. When a customer asks about their booking after it's confirmed, provide ALL available booking details including date, time, service type, and especially the booking ID.
                    4. If the customer asks "Did I book a booking?" or "What is my booking ID?" or similar questions after a successful booking, ALWAYS confirm that they did and provide the complete booking details.
                    5. NEVER suggest booking the same service again if a booking is already confirmed.
                    6. Recognize tool response messages that contain booking confirmation details, and use this information to answer customer questions about their booking.
                    7. If the booking ID appears in any previous message (including tool responses), make sure to include it when the customer asks about their booking.



                    ##RULES AND GUARDRAILS
                    1. NEVER share or acknowledge that you are an AI. Present yourself as {agent_config.agent_name}, a human representative of {business.businessName}.
                    2. NEVER make up information that hasn't been provided in the prompt.
                    3. NEVER discuss politics, religion, or controversial topics.
                    4. NEVER provide personal opinions on matters outside of cleaning services.
                    5. ALWAYS be polite, professional, and respectful.
                    6. ALWAYS prioritize appointment bookings and lead conversion.
                    7. NEVER agree to unreasonable requests (extreme discounts, services outside business scope).
                    8. NEVER ask for sensitive information like credit card details or social security numbers.
                    9. KEEP responses concise and focused on cleaning services and booking appointments.
                    10. IF you don't know something, say "I'll need to check with our team on that" instead of making up an answer.
                    11. ALWAYS verify appointment details by repeating them back to the customer.
                    12. PRIORITIZE collecting name, address, phone number, date/time, and service type for bookings.
                    13. IF the customer seems hesitant or has objections, address their concerns professionally.
                    14. NEVER discuss internal business operations or pricing strategies beyond what's needed for a booking.
                    15. ALWAYS follow up with a question to keep the conversation going.
                    16. WHEN discussing pricing, always mention the value and benefits of the service.
                    17. ALWAYS follow local business hours and availability constraints.
                    18. NEVER make promises about specific cleaning staff or results that can't be guaranteed.
                    19. MAINTAIN a friendly, helpful, and solutions-oriented tone throughout the conversation.
                    20. IF a customer is upset, acknowledge their feelings and offer practical solutions.

                    
                    ##HANDLING DIFFICULT SCENARIOS
                    1. If customer asks for a discount:
                       - Don't immediately reject, but explain the value proposition
                       - Suggest a lower-cost service option if available
                       - Only offer standard promotions that have been explicitly mentioned in the prompt
                    
                    2. If customer is angry or frustrated:
                       - Acknowledge their feelings without being defensive
                       - Apologize for any inconvenience without admitting fault
                       - Focus on what you CAN do rather than what you CAN'T do
                       - Offer to have a manager contact them if the issue is complex
                    
                    3. If customer makes inappropriate comments:
                       - Politely redirect the conversation back to cleaning services
                       - If persistent, say "I'm here to help with your cleaning needs. How can I assist you with that today?"
                       - Remain professional and focused on business matters
                    
                    4. If customer has unrealistic expectations:
                       - Gently clarify what services can realistically provide
                       - Offer alternatives that meet their needs within service limitations
                       - Be honest about limitations without being negative
                    
                    5. If customer is indecisive:
                       - Ask specific questions to narrow down their needs
                       - Suggest the most popular service option for their situation
                       - Reassure them about quality and satisfaction guarantees
                    
                    6. If customer is comparing to competitors:
                       - Focus on unique value propositions
                       - Never disparage competitors
                       - Emphasize quality, reliability, and customer satisfaction

                    ##RESPONSE GUIDELINES FOR SMS
                    1. KEEP MESSAGES CONCISE: Each message should be clear and to the point.
                    2. AVOID LONG PARAGRAPHS: Break up information into shorter sentences.
                    3. USE SIMPLE LANGUAGE: Avoid complex terminology or jargon.
                    4. INCLUDE WHITESPACE: Leave a line between paragraphs for readability.
                    5. PRIORITIZE INFORMATION: Most important details should come first.
                    6. ASK ONE QUESTION AT A TIME: Don't overwhelm the customer with multiple questions.
                    7. USE EMOJIS SPARINGLY: One or two emojis maximum per message for a friendly tone.
                    8. BE DIRECT: State the most important information clearly and early.
                    9. USE LISTS SPARINGLY: When presenting options, use short numbered lists.
                    10. END WITH CLEAR NEXT STEPS: Every message should guide the customer to the next action.
                    11. AVOID ALL CAPS: Use normal capitalization except for single words for emphasis.
                    12. STAY ON TOPIC: Each message should have a clear purpose related to booking.

                    ##SCRIPT
                    {agent_config.prompt or ''}
                    
                    ##CRITICAL TOOL USAGE INSTRUCTIONS:
                    You have access to the following tools to help with the booking process. YOU MUST USE THESE TOOLS when appropriate:

                    1. check_availability: ALWAYS USE THIS TOOL whenever a customer asks about availability or scheduling for a specific date/time
                       - Input: A date and time string (e.g., "Tomorrow at 2 PM", "March 15, 2025 at 10 AM")
                       - When to use: IMMEDIATELY when a customer mentions ANY specific date or time for booking
                       - Example trigger phrases: "Is next Monday available?", "Can I book for tomorrow?", "Do you have availability on Friday?"

                    2. bookAppointment: Use this tool to book an appointment after collecting all required customer information
                       - When to use: After confirming availability and collecting all required customer information
                       - DO NOT use this tool if a booking has already been confirmed in the conversation unless the customer explicitly asks for a new/additional booking

                    3. current_time: Use this tool to get the current time in Chicago timezone
                       - When to use: When a customer asks about current time, business hours, or what time it is
                       - Example trigger phrases: "What time is it?", "What is the current time?", "What time is it now?"

                    4. calculateTotal: Use this tool to calculate the total cost of the appointment
                       - When to use: Before booking an appointment and after confirming all customer details

                    5. rescheduleAppointment: Use this tool to reschedule an existing appointment to a new date and time
                       - Input: The booking ID and a new date and time string
                       - When to use: When a customer wants to change the date/time of an existing booking
                       - Example trigger phrases: "I need to reschedule my appointment", "Can I change my booking to next Tuesday?", "Move my appointment to 3 PM"
                       - Make sure you have the booking ID before using this tool

                    6. cancelAppointment: Use this tool to cancel an existing appointment
                       - Input: The booking ID
                       - When to use: When a customer wants to cancel their appointment
                       - Example trigger phrases: "I need to cancel my appointment", "Cancel my booking", "I don't want the cleaning anymore"
                       - Make sure you have the booking ID before using this tool

                    """
                
                return system_prompt
                
            except AgentConfiguration.DoesNotExist:
                # No configuration exists, return 0 to indicate this
                return 0
                
        except Business.DoesNotExist:
            # Business doesn't exist, return 0 to indicate this
            return 0
        except Exception as e:
            print(f"Error generating dynamic system prompt: {str(e)}")
            print(traceback.format_exc())
            return 0
    
    @staticmethod
    def get_or_create_chat(business_id, client_phone_number, session_key):
        """Get or create a chat session for a client
        
        Args:
            business_id: The ID of the business
            client_phone_number: The phone number of the client
            session_key: The session key of the client
        Returns:
            Chat object or None if error
        """
        try:
            print(f"[DEBUG] get_or_create_chat called with business_id={business_id}, client_phone_number={client_phone_number}, session_key={session_key}")
            
            # Get the business object
            business = Business.objects.get(businessId=business_id)
            print(f"[DEBUG] Found business: {business.businessName}")
            
            # Try to get an existing chat
            try:
                if client_phone_number:
                    from .utils import find_by_phone_number
                    chat = find_by_phone_number(Chat, 'clientPhoneNumber', client_phone_number, business)
                    
                    if not chat:
                        chat = Chat.objects.create(
                            business=business,
                            clientPhoneNumber=client_phone_number,
                            status='pending'  # Add default status
                        )
                           
                    print(f"[DEBUG] Created new chat ID={chat.id}")
                    return chat
                else:
                    # Check if multiple chats exist for this session key
                    chats = Chat.objects.filter(sessionKey=session_key)
                    if chats.exists():
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for session key {session_key}. Using the most recent one.")
                            # Log the chat IDs for debugging
                            for i, chat in enumerate(chats):
                                print(f"[DEBUG] Chat {i+1}: ID={chat.id}, Created={chat.createdAt}")
                            
                            # Get the most recent chat
                            chat = chats.order_by('-createdAt').first()
                            
                            # Delete older duplicate chats to prevent future issues
                            chats.exclude(id=chat.id).delete()
                            print(f"[DEBUG] Deleted older duplicate chats. Keeping chat ID={chat.id}")
                        else:
                            chat = chats.first()
                    else:
                        chat = Chat.objects.create(
                            business=business,
                            sessionKey=session_key,
                            status='pending'  # Add default status
                        )
                        print(f"[DEBUG] Created new chat ID={chat.id}")
                
                print(f"[DEBUG] Using existing chat ID={chat.id}")
                return chat
                
            except Chat.DoesNotExist:
                pass
                
                
        except Business.DoesNotExist:
            print(f"[DEBUG] Business not found with ID: {business_id}")
            return None
        except Exception as e:
            print(f"[DEBUG] Error getting or creating chat: {str(e)}")
            traceback.print_exc()
            return None
    
    @staticmethod
    def get_chat_messages(client_phone_number, session_key):
        """Get all messages for a chat session
        
        Args:
            client_phone_number: The phone number of the client
            session_key: The session key of the client
        Returns:
            List of message dictionaries or empty list if error
        """
        try:
            print(f"[DEBUG] get_chat_messages called with client_phone_number={client_phone_number}, session_key={session_key}")
            
            # Get the chat object
            if client_phone_number:
                # Check if multiple chats exist for this phone number
                chats = Chat.objects.filter(clientPhoneNumber=client_phone_number)
                if chats.count() > 1:
                    print(f"[WARNING] Found {chats.count()} chats for phone number {client_phone_number} in get_chat_messages. Using the most recent one.")
                    # Log the chat IDs for debugging
                    for i, chat in enumerate(chats):
                        print(f"[DEBUG] Chat {i+1}: ID={chat.id}, Created={chat.createdAt}")
                    
                    # Get the most recent chat
                    chat = chats.order_by('-createdAt').first()
                elif chats.count() == 0:
                    print(f"[DEBUG] No chat found for phone number: {client_phone_number}")
                    return []
                else:
                    chat = chats.first()
            else:
                # Check if multiple chats exist for this session key
                chats = Chat.objects.filter(sessionKey=session_key)
                if chats.count() > 1:
                    print(f"[WARNING] Found {chats.count()} chats for session key {session_key} in get_chat_messages. Using the most recent one.")
                    # Log the chat IDs for debugging
                    for i, chat in enumerate(chats):
                        print(f"[DEBUG] Chat {i+1}: ID={chat.id}, Created={chat.createdAt}")
                    
                    # Get the most recent chat
                    chat = chats.order_by('-createdAt').first()
                elif chats.count() == 0:
                    print(f"[DEBUG] No chat found for session key: {session_key}")
                    return []
                else:
                    chat = chats.first()
            
            print(f"[DEBUG] Getting messages for chat ID={chat.id}")
            
            # Get all messages for this chat
            messages = Messages.objects.filter(chat=chat).order_by('createdAt')
            
            # Convert to a list of dictionaries
            message_list = []
            for msg in messages:
                if msg.role == 'tool':
                    message_list.append({
                        'id': msg.id,
                        'role': 'tool',
                        'content': msg.message,  # Use content key for OpenAI compatibility
                        'createdAt': msg.createdAt
                    })
                else:
                    message_list.append({
                        'id': msg.id,
                        'role': msg.role,
                        'content': msg.message,
                        'createdAt': msg.createdAt
                    })
            
            print(f"[DEBUG] Retrieved {len(message_list)} messages from chat ID={chat.id}")
            return message_list
            
        except Chat.DoesNotExist:
            print(f"[DEBUG] Chat not found for phone number: {client_phone_number}")
            return []
        except Exception as e:
            print(f"[DEBUG] Error getting chat messages: {str(e)}")
            traceback.print_exc()
            return []
    
    @staticmethod
    def format_messages_for_openai(messages, system_prompt):
        """Format messages for OpenAI API
        
        Args:
            messages: List of message dictionaries
            system_prompt: System prompt to use
            
        Returns:
            List of message dictionaries formatted for OpenAI API
        """
        try:
            # Create the formatted messages list
            formatted_messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Add all user and assistant messages, convert tool messages to assistant
            for msg in messages:
                if 'role' in msg:
                    # Check if the message has 'content' or 'message' key
                    content = msg.get('content') or msg.get('message')
                    if content:  # Only add if there's content
                        # Convert tool messages to assistant messages with stringified content
                        if msg['role'] == 'tool':
                            # If it's a JSON string, leave it as is, otherwise stringify it
                            if not isinstance(content, str) or (isinstance(content, str) and not content.startswith('{')):
                                content = f"Tool Response: {str(content)}"
                            formatted_messages.append({
                                "role": "assistant",
                                "content": content
                            })
                        # Convert function_call to tool role
                        elif msg['role'] == 'function_call':
                            formatted_messages.append({
                                "role": "tool",
                                "content": content
                            })
                        else:
                            formatted_messages.append({
                                "role": msg['role'],
                                "content": content
                            })
            
            return formatted_messages
            
        except Exception as e:
            print(f"[ERROR] Error formatting messages for OpenAI: {str(e)}")
            traceback.print_exc()
            return [{"role": "system", "content": system_prompt}]
    
    @staticmethod
    def execute_tool_call(tool_name, tool_args_raw, client_phone_number, business, session_key=None):
        """Execute a tool call from the OpenAI API
        
        Args:
            tool_name: The name of the tool to execute
            tool_args_raw: The arguments for the tool
            client_phone_number: The phone number of the client
            business: The business object
            session_key: Optional session key for web chat
            
        Returns:
            String with the result of the tool call
        """
        print(f"\n[DEBUG] Executing tool call: {tool_name}")
        print(f"[DEBUG] Tool arguments: {tool_args_raw}")
        
        if client_phone_number is None and session_key is None:
            print("[ERROR] Missing client phone number and session key")
            return json.dumps({
                "error": "Missing client identification"
            })
            
        # Parse the tool arguments
        try:
            if isinstance(tool_args_raw, str):
                tool_args = json.loads(tool_args_raw)
            else:
                tool_args = tool_args_raw
        except Exception as e:
            print(f"[ERROR] Error parsing tool arguments: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "error": f"Error parsing tool arguments: {str(e)}"
            })
            
        # Import tools from api_views.py
        from .api_views import calculate_total, check_availability, book_appointment, get_current_time_in_chicago, reschedule_appointment, cancel_appointment

        # Handle tool calls
        try:
            # checkAvailability tool
            if tool_name == 'checkAvailability':
                print(f"\n[DEBUG] Executing checkAvailability tool with args: {tool_args}")
                date_str = tool_args.get('date')
                print(f"[DEBUG] Checking availability for date: {date_str}")
                print(f"[DEBUG] Business details: ID={business.businessId}, Name={business.businessName}")
                
                if not date_str:
                    print("[DEBUG] Missing date parameter in checkAvailability")
                    return json.dumps({
                        "error": "Missing date parameter"
                    })
                
                try:    
                    # Call the check_availability function from api_views.py
                    print(f"[DEBUG] Calling check_availability function with business ID={business.businessId} and date={date_str}")
                    result = check_availability(business, date_str)
                    print(f"[DEBUG] check_availability returned: {result}")
                    return json.dumps(result)
                except Exception as e:
                    print(f"[ERROR] Error in checkAvailability: {str(e)}")
                    traceback.print_exc()
                    return json.dumps({
                        "error": f"Error checking availability: {str(e)}"
                    })
                
            # calculateTotal tool
            elif tool_name == 'calculateTotal':
                print(f"[DEBUG] Using client_phone_number={client_phone_number}, session_key={session_key}")
                
                try:
                    # Handle potential multiple chats
                    if client_phone_number:
                        chats = Chat.objects.filter(clientPhoneNumber=client_phone_number)
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for phone number {client_phone_number} in calculateTotal. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                        elif chats.count() == 0:
                            return json.dumps({
                                "success": False,
                                "message": "No chat found for this phone number. Please try again."
                            })
                        else:
                            chat = chats.first()
                    elif session_key:
                        chats = Chat.objects.filter(sessionKey=session_key)
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for session key {session_key} in calculateTotal. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                        elif chats.count() == 0:
                            return json.dumps({
                                "success": False,
                                "message": "No chat found for this session. Please try again."
                            })
                        else:
                            chat = chats.first()
                    else:
                        return json.dumps({
                            "success": False,
                            "message": "No client identifier found. Please try again."
                        })
                    
                    # Get chat messages and format for summary extraction
                    messages = OpenAIAgent.get_chat_messages(client_phone_number, session_key)
                    formatted_messages = []
                    for msg in messages:
                        if isinstance(msg, dict) and 'role' in msg:
                            # Handle different message formats
                            content = msg.get('content') or msg.get('message')
                            if content:
                                formatted_messages.append({
                                    'role': msg['role'],
                                    'content': content
                                })
                        
                    # Extract summary from conversation
                    summary = OpenAIAgent.extract_conversation_summary(formatted_messages, business.businessId)
                
                    
                    # Save summary to chat object
                    chat.summary = summary
                    chat.save()
                
                  
                    
                    # Get the chat using either phone number or session key
                    if client_phone_number:
                        # Call the calculate_total function from api_views.py
                        result = calculate_total(business, client_phone_number=client_phone_number)
                    else:
                        # For session-based chats, we need to retrieve the chat and then call calculate_total
                        result = calculate_total(business, session_key=session_key)
                    
                    return json.dumps(result)
                except Exception as e:
                    print(f"[ERROR] Error in calculateTotal: {str(e)}")
                    traceback.print_exc()
                    return json.dumps({
                        "error": f"Error executing calculateTotal tool: {str(e)}"
                    })
                
            # bookAppointment tool
            elif tool_name == 'bookAppointment':
                # Extract summary from conversation
                try:
                    # Handle potential multiple chats
                    if client_phone_number:
                        chats = Chat.objects.filter(clientPhoneNumber=client_phone_number)
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for phone number {client_phone_number} in bookAppointment. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                        elif chats.count() == 0:
                            return json.dumps({
                                "success": False,
                                "message": "No chat found for this phone number. Please try again."
                            })
                        else:
                            chat = chats.first()
                    elif session_key:
                        chats = Chat.objects.filter(sessionKey=session_key)
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for session key {session_key} in bookAppointment. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                        elif chats.count() == 0:
                            return json.dumps({
                                "success": False,
                                "message": "No chat found for this session. Please try again."
                            })
                        else:
                            chat = chats.first()
                    else:
                        return json.dumps({
                            "success": False,
                            "message": "No client identifier found. Please try again."
                        })
                    
                    # Get chat messages and format for summary extraction
                    messages = OpenAIAgent.get_chat_messages(client_phone_number, session_key)
                    formatted_messages = []
                    for msg in messages:
                        if isinstance(msg, dict) and 'role' in msg:
                            # Handle different message formats
                            content = msg.get('content') or msg.get('message')
                            if content:
                                formatted_messages.append({
                                    'role': msg['role'],
                                    'content': content
                                })
                        
                    # Extract summary from conversation
                    summary = OpenAIAgent.extract_conversation_summary(formatted_messages, business.businessId)
                    
                  
                    # Save summary to chat object
                    chat.summary = summary
                    chat.save()
                    
                 
                   
                    if client_phone_number:
                        result = book_appointment(business, client_phone_number=client_phone_number)
                        
                    elif session_key:
                        result = book_appointment(business, session_key=session_key)


                    else:
                        result = {
                            "success": False,
                            "error": "No phone number or session key available"
                        }
                    if result.get('success') and result.get('booking_id'):
                        # Update summary with booking ID
                        if not isinstance(chat.summary, dict):
                            chat.summary = {}
                        chat.summary['bookingId'] = result.get('booking_id')
                        chat.save()
                        print(f"[DEBUG] Updated chat summary with booking ID: {result.get('booking_id')}")
                
                    return json.dumps(result)
                except Exception as e:
                    print(f"[ERROR] Error in bookAppointment: {str(e)}")
                    traceback.print_exc()
                    return json.dumps({
                        "error": f"Error booking appointment: {str(e)}"
                    })
                    
            # getCurrentTime tool
            elif tool_name == 'getCurrentTime':
                # Call the get_current_time_in_chicago function with business parameter
                result = get_current_time_in_chicago(business)
                return json.dumps({
                    "current_time": result
                })
                
            # rescheduleAppointment tool
            elif tool_name == 'rescheduleAppointment':
                print(f"[DEBUG] Executing rescheduleAppointment tool with args: {tool_args}")
                booking_id = tool_args.get('booking_id')
                new_date_time = tool_args.get('new_date_time')
                
                if not booking_id or not new_date_time:
                    print("[DEBUG] Missing required parameters in rescheduleAppointment")
                    return json.dumps({
                        "success": False,
                        "error": "Missing required parameters (booking_id or new_date_time)"
                    })
                    
                try:
                    # Call the reschedule_appointment function from api_views.py
                    print(f"[DEBUG] Calling reschedule_appointment function with business ID={business.businessId}, booking_id={booking_id}, new_date_time={new_date_time}")
                    result = reschedule_appointment(business, booking_id, new_date_time)
                    print(f"[DEBUG] reschedule_appointment returned: {result}")
                    return json.dumps(result)
                except Exception as e:
                    print(f"[ERROR] Error in rescheduleAppointment: {str(e)}")
                    traceback.print_exc()
                    return json.dumps({
                        "success": False,
                        "error": f"Error rescheduling appointment: {str(e)}"
                    })
                
            # cancelAppointment tool
            elif tool_name == 'cancelAppointment':
                print(f"[DEBUG] Executing cancelAppointment tool with args: {tool_args}")
                booking_id = tool_args.get('booking_id')
                
                if not booking_id:
                    print("[DEBUG] Missing booking_id parameter in cancelAppointment")
                    return json.dumps({
                        "success": False,
                        "error": "Missing booking_id parameter"
                    })
                    
                try:
                    # Call the cancel_appointment function from api_views.py
                    print(f"[DEBUG] Calling cancel_appointment function with business ID={business.businessId}, booking_id={booking_id}")
                    result = cancel_appointment(business, booking_id)
                    print(f"[DEBUG] cancel_appointment returned: {result}")
                    return json.dumps(result)
                except Exception as e:
                    print(f"[ERROR] Error in cancelAppointment: {str(e)}")
                    traceback.print_exc()
                    return json.dumps({
                        "success": False,
                        "error": f"Error canceling appointment: {str(e)}"
                    })
                
            else:
                return json.dumps({
                    "error": f"Unknown tool: {tool_name}"
                })
                
        except Exception as e:
            print(f"[ERROR] Error executing tool call: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "error": f"Error executing tool call: {str(e)}"
            })
    
    @staticmethod
    def get_openai_tools():
        """Get the available tools for the agent
        
        Returns:
            List of tool definitions
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "checkAvailability",
                    "description": "Check if a given date and time is available for booking",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The date and time to check availability for, in natural language (e.g. 'tomorrow at 10am', 'next Monday at 2pm')"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculateTotal",
                    "description": "Calculate the total price based on the customer details",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bedrooms": {
                                "type": "integer",
                                "description": "Number of bedrooms"
                            },
                            "bathrooms": {
                                "type": "integer",
                                "description": "Number of bathrooms"
                            },
                            "extras": {
                                "type": "array",
                                "description": "List of extra services (deep_clean, fridge_cleaning, oven_cleaning, window_cleaning, cabinet_cleaning)",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["bedrooms", "bathrooms"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bookAppointment",
                    "description": "Book an appointment based on the customer details collected during the conversation",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "getCurrentTime",
                    "description": "Get the current time in Chicago timezone",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rescheduleAppointment",
                    "description": "Reschedule an existing appointment to a new date and time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "string",
                                "description": "The booking ID of the appointment to reschedule"
                            },
                            "new_date_time": {
                                "type": "string",
                                "description": "The new date and time for the appointment in natural language (e.g. 'tomorrow at 10am', 'next Monday at 2pm')"
                            }
                        },
                        "required": ["booking_id", "new_date_time"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancelAppointment",
                    "description": "Cancel an existing appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "string",
                                "description": "The booking ID of the appointment to cancel"
                            }
                        },
                        "required": ["booking_id"]
                    }
                }
            }
        ]
        
        return tools
    
    @staticmethod
    def process_ai_response(response, client_phone_number, business, session_key=None):
        """Process the AI response from OpenAI API
        
        Args:
            response: The response from OpenAI API
            client_phone_number: The phone number of the client
            business: The business object
            session_key: The session key for web chat (added parameter)
            
        Returns:
            Dictionary with response content and any tool call results
        """
        try:
            # Extract the response content
            content = response.choices[0].message.content or ""
            
            # Check if there are any tool calls
            tool_calls = response.choices[0].message.tool_calls
            
            if tool_calls:
                print(f"[DEBUG] Found {len(tool_calls)} tool calls in response")
                
                # Process each tool call
                tool_call_results = []
                for tool_call in tool_calls:
                    try:
                        # Execute the tool call
                        result = OpenAIAgent.execute_tool_call(
                            tool_call.function.name,
                            tool_call.function.arguments,
                            client_phone_number,
                            business,
                            session_key  # Pass session_key to execute_tool_call
                        )
                        
                        # Add to results
                        tool_call_results.append({
                            'tool_call_id': tool_call.id,
                            'result': result
                        })
                    except Exception as e:
                        print(f"[ERROR] Error executing tool call: {str(e)}")
                        traceback.print_exc()
                        tool_call_results.append({
                            'tool_call_id': tool_call.id,
                            'result': json.dumps({
                                "error": f"Error executing tool call: {str(e)}"
                            })
                        })
                
                # Now we need to generate a follow-up response based on the tool results
                # First, prepare the messages for the follow-up call
                messages = []
                
                # Add a more detailed system prompt that ensures continuity with the business script
                system_prompt = f"""You are Sarah, an SMS agent for {business.businessName}, a professional cleaning company. 
                                    
                    You MUST follow these instructions when responding after tool calls:
                    1. Generate a natural, conversational response based on the tool results
                    2. NEVER mention that you're using tools, APIs, or checking systems
                    3. Speak as if you naturally know this information
                    4. Maintain the conversation flow from before the tool call - continue where you left off
                    5. Follow up with the next logical step in the conversation based on your script
                    6. If you were collecting information before the tool call, continue collecting any missing information
                    7. If the tool provided availability or pricing, confirm it and ask if the customer wants to proceed with booking
                    8. If the tool completed a booking, Ask client to pay by clicking on the link received through sms and email and ask if there's anything else they need
                    9. Keep your tone friendly, professional, and conversational
                    10. Remember your role is to guide the customer through the entire booking process

                    Your primary goal is to collect all necessary information and complete the booking process efficiently.
                """
                messages.append({"role": "system", "content": system_prompt})
                
                # Get the chat using either phone number or session key
                try:
                    # Handle getting the chat based on available identifiers
                    print(f"[DEBUG] process_ai_response trying to get chat with client_phone_number={client_phone_number} or session_key={session_key}")
                    
                    # Ensure we have access to the models
                    from .models import Chat, Messages, AgentConfiguration
                    print(f"[DEBUG] Successfully imported models")
                    
                    if client_phone_number:
                        # Handle potential multiple chats with the same phone number
                        chats = Chat.objects.filter(clientPhoneNumber=client_phone_number)
                        print(f"[DEBUG] Found {chats.count()} chats with phone number {client_phone_number}")
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for phone number {client_phone_number} in process_ai_response. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                            # Print chat details for debugging
                            print(f"[DEBUG] Selected chat ID={chat.id}, created={chat.createdAt}, clientPhone={chat.clientPhoneNumber}, sessionKey={chat.sessionKey}")
                        elif chats.count() == 0:
                            chat = None
                            print(f"[WARNING] No chat found for phone number {client_phone_number}")
                        else:
                            chat = chats.first()
                            print(f"[DEBUG] Selected chat ID={chat.id}, created={chat.createdAt}, clientPhone={chat.clientPhoneNumber}, sessionKey={chat.sessionKey}")
                    elif session_key:
                        # Handle potential multiple chats with the same session key
                        chats = Chat.objects.filter(sessionKey=session_key)
                        print(f"[DEBUG] Found {chats.count()} chats with session key {session_key}")
                        if chats.count() > 1:
                            print(f"[WARNING] Found {chats.count()} chats for session key {session_key} in process_ai_response. Using the most recent one.")
                            chat = chats.order_by('-createdAt').first()
                            # Print chat details for debugging
                            print(f"[DEBUG] Selected chat ID={chat.id}, created={chat.createdAt}, clientPhone={chat.clientPhoneNumber}, sessionKey={chat.sessionKey}")
                        elif chats.count() == 0:
                            chat = None
                            print(f"[WARNING] No chat found for session key {session_key}")
                        else:
                            chat = chats.first()
                            print(f"[DEBUG] Selected chat ID={chat.id}, created={chat.createdAt}, clientPhone={chat.clientPhoneNumber}, sessionKey={chat.sessionKey}")
                    else:
                        chat = None
                        print("[WARNING] No client phone number or session key provided in process_ai_response.")
                        
                    print(f"[DEBUG] Using chat ID={chat.id if chat else 'None'} in process_ai_response")
                
                    # Add context about the current conversation state to help the AI continue properly
                    if chat and hasattr(chat, 'summary') and chat.summary:
                        # Extract relevant context from the chat summary
                        context_prompt = "Current conversation context:\n"
                        
                        # Add collected customer information
                        customer_info = []
                        for field in ['firstName', 'lastName', 'email', 'phoneNumber', 'address']:
                            if chat.summary.get(field):
                                customer_info.append(f"- {field}: {chat.summary.get(field)}")
                        
                        if customer_info:
                            context_prompt += "\nCustomer information collected:\n" + "\n".join(customer_info) + "\n"
                        
                        # Add property details if available
                        property_info = []
                        for field in ['bedrooms', 'bathrooms', 'squareFeet', 'serviceType']:
                            if chat.summary.get(field):
                                property_info.append(f"- {field}: {chat.summary.get(field)}")
                        
                        if property_info:
                            context_prompt += "\nProperty details collected:\n" + "\n".join(property_info) + "\n"
                        
                        # Add conversation stage information
                        if chat.summary.get('conversationStage'):
                            context_prompt += f"\nCurrent conversation stage: {chat.summary.get('conversationStage')}\n"
                            
                        # Add this context to the messages
                        messages.append({"role": "system", "content": context_prompt})
                        
                except Exception as e:
                    print(f"[ERROR] Error retrieving chat in process_ai_response: {str(e)}")
                    traceback.print_exc()
                
                # Add the original assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in tool_calls]
                })
                
                # Add the tool results
                for tool_result in tool_call_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_result["tool_call_id"],
                        "content": tool_result["result"]
                    })
                
                try:
                    # Call OpenAI again to generate a response based on the tool results
                    print(f"[DEBUG] Calling OpenAI to generate response based on tool results")
                    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                    follow_up_response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        temperature=0.5,
                        max_tokens=1000
                    )
                    
                    # Extract the follow-up response content
                    follow_up_content = follow_up_response.choices[0].message.content or ""
                    print(f"[DEBUG] Follow-up response: {follow_up_content[:100]}...")
                    
                    # Return both the original content, tool results, and follow-up content
                    return {
                        'content': follow_up_content,  # Use the follow-up content as the main response
                        'original_content': content,   # Keep the original content for reference
                        'tool_call_results': tool_call_results
                    }
                except Exception as e:
                    print(f"[ERROR] Error generating follow-up response: {str(e)}")
                    traceback.print_exc()
                    # Fall back to returning the original content and tool results
                    return {
                        'content': "I'm sorry, I encountered an error processing your request. Please try again.",
                        'original_content': content,
                        'tool_call_results': tool_call_results,
                        'error': str(e)
                    }
                
            else:
                # No tool calls, just return the content
                return {
                    'content': content
                }
                
        except Exception as e:
            print(f"[ERROR] Error processing AI response: {str(e)}")
            traceback.print_exc()
            return {
                'content': "I'm sorry, I encountered an error processing your request. Please try again.",
                'error': str(e)
            }
    
    @staticmethod
    def extract_conversation_summary(chat_history, business_id=None):
        """
        Extract key information from the conversation history for booking purposes using OpenAI LLM.
        
        Args:
            chat_history: List of message dictionaries with 'role' and 'content' or 'message' keys
            
        Returns:
            Dictionary with extracted customer information
        """
        


        # Initialize empty summary with default values
        summary = {
            'firstName': '',
            'lastName': '',
            'email': '',
            'phoneNumber': '',
            'address1': '',
            'city': '',
            'state': '',
            'zipCode': '',
            'squareFeet': '',
            'bedrooms': '',
            'bathrooms': '',
            'serviceType': '',
            'appointmentDateTime': '',
            'convertedDateTime': '',
            'otherRequests': '',
            'detailSummary': '',
            "addonDishes": '',
            "addonLaundryLoads": '',
            "addonWindowCleaning": '',
            "addonPetsCleaning": '',
            "addonFridgeCleaning": '',
            "addonOvenCleaning": '',
            "addonBaseboard": '',
            "addonBlinds": '',
            "addonGreenCleaning": '',
            "addonCabinetsCleaning": '',
            "addonPatioSweeping": '',
            "addonGarageSweeping": '',
            'bookingId': ''
        }
        

        if business_id:
            business = Business.objects.get(businessId=business_id)
            customAddons = CustomAddons.objects.filter(business=business)
            custom_addon_fields = "\n".join([f'            - {addon.addonDataName}: Quantity of {addon.addonName} Addon' for addon in customAddons])
            for addon in customAddons:
                summary[addon.addonDataName] = ''

        try:
            print(f"[DEBUG] Starting conversation summary extraction at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
            
            # Filter to only include user and assistant messages - process all messages without limit
            filtered_messages = []
            for msg in chat_history:  # Process all messages
                # Handle different message formats
                if isinstance(msg, dict):
                    role = msg.get('role')
                    # Try to get content from either 'content' or 'message' key
                    content = msg.get('content') or msg.get('message')
                    
                    if role and content:
                        filtered_messages.append({'role': role, 'content': content})
                        
            # Log the message processing results
            print(f"[DEBUG] Processed {len(chat_history)} messages into {len(filtered_messages)} filtered messages")
            
            # Skip if conversation is too short
            if len(filtered_messages) < 2:
                print(f"[DEBUG] Conversation too short to extract summary: {len(filtered_messages)} messages")
                return summary
                
            # Join messages into a single text for analysis, but with clear role indicators
            conversation_text = ""
            for msg in filtered_messages:
                role = "Customer" if msg['role'] == 'user' else "Agent"
                conversation_text += f"{role}: {msg['content']}\n"
            
            print(f"[DEBUG] Extracting summary from conversation: {len(conversation_text)} chars, {len(filtered_messages)} messages")
            
            # Create a detailed system prompt for OpenAI to extract comprehensive information
            system_prompt = f"""
            You are an AI assistant for Cleaning Biz, a professional cleaning service. Your task is to extract specific customer booking information from this conversation.
            Analyze the entire conversation history carefully and extract all relevant details.
            
            Respond ONLY with a valid JSON object containing these keys (leave empty if not found):
            - firstName: Customer's first name
            - lastName: Customer's last name empty if not found
            - email: Customer's email address
            - phoneNumber: Customer's phone number with country code without any spaces or dashes
            - address1: Street address (just the street part, no city/state/zip)
            - city: City name
            - state: State
            - zipCode: 5-digit or 9-digit zip code
            - squareFeet: Square footage of the property as a numeric string
            - bedrooms: Number of bedrooms as a numeric string
            - bathrooms: Number of bathrooms as a numeric string
            - serviceType: Type of service requested (e.g., "regular cleaning", "deep cleaning", "move-in")
            - appointmentDateTime: Appointment date and time in ANY format mentioned in the conversation
            - convertedDateTime: Convert Appointment date and time to a standard format (YYYY-MM-DD HH:MM) Current Time is: {get_current_time_in_chicago()}
            - otherRequests: Any special requests or notes
            - detailSummary: Summary of the Whole conversation
            - addonDishes: Quantity of Dishes Addon
            - addonLaundryLoads: Quantity of Laundry Loads Addon
            - addonWindowCleaning: Quantity of Window Cleaning Addon
            - addonPetsCleaning: Quantity of Pets Cleaning Addon
            - addonFridgeCleaning: Quantity of Fridge Cleaning Addon
            - addonOvenCleaning: Quantity of Oven Cleaning Addon
            - addonBaseboard: Quantity of Baseboard Addon
            - addonBlinds: Quantity of Blinds Addon
            - addonGreenCleaning: Quantity of Green Cleaning Addon
            - addonCabinetsCleaning: Quantity of Cabinets Cleaning Addon
            - addonPatioSweeping: Quantity of Patio Sweeping Addon
            - addonGarageSweeping: Quantity of Garage Sweeping Addon
            {custom_addon_fields}
            
            - bookingId: Booking ID if available

            ONLY return a valid JSON object. No explanations or additional text.
            If you cannot determine a value, leave it as an empty string.
            """
            
            # Initialize OpenAI client
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            
            # Call OpenAI API for extraction with full token allocation for comprehensive extraction
            response = client.chat.completions.create(
                model="gpt-4o",  # Using the most capable model for accurate extraction
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversation_text}
                ],
                temperature=0.1,  # Low temperature for more deterministic extraction
                max_tokens=1000,  # Using full token allocation for comprehensive extraction
                response_format={"type": "json_object"}
            )
            
            print(f"[DEBUG] Extraction API call completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
            
            # Extract the response content
            extracted_info = response.choices[0].message.content
            print(f"[DEBUG] Raw extraction response: {extracted_info[:200]}...")
            
            try:
                # Parse the JSON response
                extracted_data = json.loads(extracted_info)
                
                # Update summary with extracted data
                for key, value in extracted_data.items():
                    if key in summary and value:
                        summary[key] = value
          
                return summary
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] Error parsing extracted information: {str(e)}")
                print(f"[ERROR] Raw extraction response: {extracted_info}")
            
        except Exception as e:
            print(f"[ERROR] Error extracting conversation summary: {str(e)}")
            print(traceback.format_exc())
        
        
        
        return summary


# Django views for OpenAI chat
@login_required
def chat_view(request):
    """View for the OpenAI chat interface
    
    Args:
        request: Django request object
        
    Returns:
        Rendered template with chat data
    """
    try:
        # Get the business for this user
        business = get_object_or_404(Business, user=request.user)
        
        # Get all chats for this business
        chats = {}
        chat_objects = Chat.objects.filter(business=business)
        
        for chat in chat_objects:
            # Get messages for this chat
            messages = Messages.objects.filter(chat=chat).order_by('-createdAt')
            if messages.exists():
                chats[chat.clientPhoneNumber] = list(messages)
        
        # Render the template
        return render(request, 'ai_agent/openai_chat.html', {
            'business': business,
            'chats': chats
        })
    except Exception as e:
        print(f"Error in chat_view: {str(e)}")
        traceback.print_exc()
        return render(request, 'ai_agent/openai_chat.html', {
            'error': str(e)
        })

@csrf_exempt
def chat_api(request):
    """API endpoint for OpenAI chat
    
    Args:
        request: Django request object
        
    Returns:
        JsonResponse with the AI response or chat messages
    """
    # Handle GET requests for retrieving messages
    if request.method == 'GET':
        try:
            client_phone_number = request.GET.get('client_phone_number')
            session_key = request.GET.get('session_key')
            action = request.GET.get('action')
            
            if action == 'get_messages' and (client_phone_number or session_key):
                # Get all messages for this chat
                messages = OpenAIAgent.get_chat_messages(client_phone_number, session_key)
                if len(messages) == 0:
                    return JsonResponse({
                        'error': 'No messages found',
                        'status': 'no_messages'
                    }, status=200)
                else:
                    return JsonResponse({
                        'messages': messages,
                        'status': 'success'
                    })
            else:
                return JsonResponse({
                    'status': 'error',
                    'error': 'Invalid action or missing phone number or session key'
                }, status=400)
            
        except Exception as e:
            print(f"Error in chat_api GET: {str(e)}")
            traceback.print_exc()
            return JsonResponse({
                'error': str(e)
            }, status=500)
    
    # Checking SMS Usage Limits

    




    # Handle POST requests for chat interaction
    try:
        # Parse the request data
        data = json.loads(request.body)
        business_id = data.get('business_id')
        client_phone_number = data.get('client_phone_number')
        session_key = data.get('session_key')
        message_text = data.get('message')

        from usage_analytics.services.usage_service import UsageService
        check_limit = UsageService.check_sms_messages_limit(Business.objects.get(businessId=business_id))
        if check_limit.get('exceeded'):
            print("SMS Limit reached for your Plan")
            return JsonResponse({
                'error': 'SMS limit exceeded'
            }, status=400)
        
       
        if not business_id or not (client_phone_number or session_key) or not message_text:
            return JsonResponse({
                'error': 'Missing required fields'
            }, status=400)
        
        # Get or create the chat
        chat = OpenAIAgent.get_or_create_chat(business_id, client_phone_number, session_key)
        if not chat:
            return JsonResponse({
                'error': 'Failed to get or create chat' 
            }, status=500)
        
        # Create a new message
        message = Messages.objects.create(
            chat=chat,
            role='user',
            message=message_text
        )
        
        # Get the system prompt
        system_prompt = OpenAIAgent.get_dynamic_system_prompt(business_id)
      
        # Get all messages for this chat
        messages = OpenAIAgent.get_chat_messages(client_phone_number, session_key)
        
        # Format messages for OpenAI
        formatted_messages = OpenAIAgent.format_messages_for_openai(messages, system_prompt)
        
        # Call OpenAI API
        try:
            print(f"[DEBUG] Calling OpenAI API")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=formatted_messages,
                temperature=0.5,
                max_tokens=5000,
                tools=OpenAIAgent.get_openai_tools()
            )
            
            # Process the response
            business = Business.objects.get(businessId=business_id)
            ai_response = OpenAIAgent.process_ai_response(response, client_phone_number, business, session_key)
            
            # Save the assistant message - only if ai_response is not None or empty
            if ai_response:
                # Create a new message for the assistant response
                Messages.objects.create(
                    chat=chat,
                    role='assistant',
                    message=ai_response['content']
                )

                # Add the assistant message to formatted_messages for summary extraction
                formatted_messages.append({
                    'role': 'assistant',
                    'content': ai_response['content']
                })
                
                # Process tool call results if any
                if 'tool_call_results' in ai_response and ai_response['tool_call_results']:
                    print(f"[DEBUG] Processing {len(ai_response['tool_call_results'])} tool call results")
                    
                    # Create tool messages for each tool call result
                    for tool_result in ai_response['tool_call_results']:
                        try:
                            # Save the tool message to the database
                            Messages.objects.create(
                                chat=chat,
                                role='tool',
                                message=tool_result['result'],
                            )
                            
                            # Add the tool message to formatted_messages
                            formatted_messages.append({
                                'role': 'assistant',
                                'content': tool_result['result'],
                            })
                        except Exception as e:
                            print(f"[ERROR] Error saving tool message: {str(e)}")
                            traceback.print_exc()
            else:
                # Handle case where ai_response is None or empty
                print("[DEBUG] Empty AI response")
                Messages.objects.create(
                    chat=chat,
                    role='assistant',
                    message="I'm sorry, I encountered an error processing your request. Please try again."
                )

            
            from .utils import get_chat_status
            chat_status = get_chat_status(chat)
            print(f"[DEBUG] Chat status: {chat_status}")
            
            # Analyze and update chat summary
            # Make sure formatted_messages is in the correct format
            # Each message should be a dictionary with 'role' and 'content' keys
            # messages_for_summary = []
            
            # # Convert all messages to the correct format
            # for msg in formatted_messages:
            #     if isinstance(msg, dict) and 'role' in msg:
            #         # Handle different message formats
            #         content = msg.get('content') or msg.get('message')
            #         if content:  # Only add messages with content
            #             messages_for_summary.append({
            #                 'role': msg['role'],
            #                 'content': content
            #             })
          
            # # Extract conversation summary if we have enough messages
            # if len(messages_for_summary) >= 2:
            #     try:
            #         # Extract conversation summary
            #         summary = OpenAIAgent.extract_conversation_summary(messages_for_summary)
                    
            #         # Add debug logs to track chat object
            #         print(f"[DEBUG] chat_api: About to save summary to chat ID={chat.id}, Phone={chat.clientPhoneNumber}, Session={chat.sessionKey}")
                    
            #         # Update chat summary in database
            #         # Make sure we're storing the summary as a JSON string
            #         if isinstance(summary, dict):
            #             chat.summary = summary
            #             chat.save()
            #             print(f"[DEBUG] Successfully saved summary to chat: {len(summary.keys())} fields")
            #         else:
            #             print(f"[DEBUG] Summary is not a dict, cannot save: {type(summary)}")
            #     except Exception as e:
            #         print(f"Error extracting conversation summary: {str(e)}")
            #         traceback.print_exc()
            
            # Return the response
            response_data = {
                'response': ai_response.get('content', '')
            }
            
            # Add original content if available
            if 'original_content' in ai_response:
                response_data['original_content'] = ai_response['original_content']
            
            # Add tool call results if any
            if 'tool_call_results' in ai_response and ai_response['tool_call_results']:
                response_data['tool_call_results'] = ai_response['tool_call_results']
            
            # Add error if any
            if 'error' in ai_response:
                response_data['error'] = ai_response['error']
            
            return JsonResponse(response_data)
            
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            traceback.print_exc()
            return JsonResponse({
                'error': f"Error calling OpenAI API: {str(e)}"
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        print(f"Error in chat_api: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)



@csrf_exempt
def delete_chat(request, client_phone_number):
    """API endpoint to delete a chat
    
    Args:
        request: Django request object
        client_phone_number: The phone number of the client
        
    Returns:
        JsonResponse with success or error message
    """
    try:
        # Get the chat object
        chat = Chat.objects.get(clientPhoneNumber=client_phone_number)
        
        # Delete all messages for this chat
        Messages.objects.filter(chat=chat).delete()
        
        # Delete the chat
        chat.delete()
        
        return JsonResponse({
            'success': True
        })
    except Chat.DoesNotExist:
        return JsonResponse({
            'error': 'Chat not found'
        }, status=404)
    except Exception as e:
        print(f"Error in delete_chat: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)
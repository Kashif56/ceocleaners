from django.db.models import Q
from datetime import datetime
import pytz
from dotenv import load_dotenv
from accounts.models import Business, BusinessSettings, CustomAddons
import os
from openai import OpenAI
import traceback
import re

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
# Change timezone to chicago
current_time = datetime.now().astimezone(pytz.timezone('America/Chicago'))



def find_by_phone_number(model, field_name, phone, business):
    """Find a record by trying different phone number formats."""

    # Extract only the last 10 digits for a more reliable comparison
    phone_digits = re.sub(r'\D', '', phone)  # Remove all non-numeric characters
    phone_last_10 = phone_digits[-10:]  # Get the last 10 digits
    
    # Build query to check different formats in a single database hit
    query = Q(**{field_name: phone}) | Q(**{field_name: phone_digits}) | Q(**{field_name: phone_last_10})
    
    return model.objects.filter(business=business).filter(query).first()


def default_prompt(business):
    try:
        business_settings = business.settings
        custom_addons = business.business_custom_addons

        # Define pricing fields by category
        base_pricing = {
            'bedroomPrice': business_settings.bedroomPrice,
            'bathroomPrice': business_settings.bathroomPrice,
            'depositFee': business_settings.depositFee,
            'taxPercent': business_settings.taxPercent
        }
        
        multipliers = {
            'Standard': business_settings.sqftMultiplierStandard,
            'Deep': business_settings.sqftMultiplierDeep,
            'Moveinout': business_settings.sqftMultiplierMoveinout,
            'Airbnb': business_settings.sqftMultiplierAirbnb
        }
        
        addons = {
            'Dishes': business_settings.addonPriceDishes,
            'Laundry': business_settings.addonPriceLaundry,
            'Window': business_settings.addonPriceWindow,
            'Pets': business_settings.addonPricePets,
            'Fridge': business_settings.addonPriceFridge,
            'Oven': business_settings.addonPriceOven,
            'Baseboard': business_settings.addonPriceBaseboard,
            'Blinds': business_settings.addonPriceBlinds,
            'Green': business_settings.addonPriceGreen,
            'Cabinets': business_settings.addonPriceCabinets,
            'Patio': business_settings.addonPricePatio,
            'Garage': business_settings.addonPriceGarage
        }
        
        # Build the pricing sections
        sections = ['#PRICINGS\n']
        
        # Filter non-zero values and format them
        non_zero_base = {k: v for k, v in base_pricing.items() if v}
        if non_zero_base:
            sections.extend([f"{k}: {v}" for k, v in non_zero_base.items()])
        
        non_zero_multipliers = {k: v for k, v in multipliers.items() if v}
        if non_zero_multipliers:
            sections.append('\n# Square Feet Multipliers')
            sections.extend([f"{k}: {v}" for k, v in non_zero_multipliers.items()])
        
        non_zero_addons = {k: v for k, v in addons.items() if v}
        if non_zero_addons:
            sections.append('\n# Add-on Prices')
            sections.extend([f"{k}: {v}" for k, v in non_zero_addons.items()])
        
        # Join all sections with proper formatting
        business_pricings = "    " + "\n    ".join(sections)

        prompt = f"""
###Role of the AI SMS Agent:
The SMS Agent acts as a virtual customer support and sales representative for {business.businessName}. It handles inbound and outbound SMS to:
Greet and engage potential customers
Confirm interest in cleaning services
Gather essential customer details (name, phone, email, address)
Collect property details (square footage, bedrooms, bathrooms)
Provide service options & pricing
Schedule and confirm cleaning appointments
Send booking confirmation and invoice links via email or SMS

The AI ensures a smooth, professional, and persuasive booking process, helping {business.businessName} secure more appointments while maintaining excellent customer experience.

###Who are {business.businessName}?
{business.businessName} is a leading professional cleaning service provider based in {business.address}. They offer top-quality residential and commercial cleaning services tailored to meet the unique needs of each client.

###{business.businessName}'s Mission:
To provide high-quality, reliable, and professional cleaning services
To ensure a clean and healthy environment for clients
To deliver 100% customer satisfaction with every service

###Services include:
Regular Cleaning â€“ Standard home maintenance cleaning
Deep Cleaning â€“ Thorough top-to-bottom cleaning (20% extra)
Commercial Cleaning â€“ Offices, businesses, and workspaces

#Pricing is in Dollars
{business_pricings}


###SMS Agent -  Script
1- Greeting & Introduction
"Hello! Thank you for contacting {business.businessName}, your trusted cleaning service in {business.address}. My name is Sarah, and Iâ€™d be happy to assist you today! How are you?"
"I wanted to check if you're interested in booking a professional cleaning service with us today?"

2- Confirming Interest & Collecting Basic Info
If the user says YES, proceed:
"Great! May I have your name, phone number, and email address so I can send you a confirmation?"

(Wait for response and collect details.)

3- Asking for Property Details
"Now, letâ€™s get some details about the space you need cleaned."

- "Can you tell me the approximate size of the area in square feet?"
- "How many bedrooms need cleaning?"
- "How many bathrooms will need to be cleaned?"
(wait for response)
Then Ask user If you like to have any addons, Give User information about [Addons] Provided in Prompt and ask for quantity for each addon

4- Asking for Type of Cleaning
"We offer three types of cleaning services:"

- Regular Cleaning: Basic home maintenance cleaning
- Deep Cleaning: Thorough cleaning, great for first-time or seasonal cleanings (+20% cost)
- Commercial Cleaning: Cleaning for offices and business spaces

"Which type of cleaning would you like?"

(Wait for response.)

"Based on your home size and the service you selected, the total cost will be $[amount]."

(Pause for response.)

6- Address & Scheduling
"May I have the full address where the cleaning will take place?"

(Wait for response.)

"Thank you! Now, what date and time would work best for you?"

(Pause for response.)

7- Handling Availability & Offering Alternative Time Slots
â³ If the chosen time slot is unavailable:

"That time isn't available, but I have three alternative slots: [Option 1], [Option 2], or [Option 3]. Which one works best for you?"

(Wait for user selection.)

8- Booking the Appointment & Confirmation
"Perfect! Let me book your appointment now. Please hold for a moment."

AI will process the booking in real-time

"Your appointment is added to system. To Confirm your Slot Please Pay the Invoice. You will receive a Link and Detail of Invoice via SMS or Email"

"Thank you for choosing {business.businessName}! We look forward to making your space shine. Have a great day!"

AI Agent Behavior Guidelines:
- Be friendly, engaging, and professional.
- Encourage hesitant customers with discounts.
- Provide clear pricing and service details.
- Confirm all booking details before finalizing.
- Use a conversational tone and allow pauses for natural interaction.
        """

        return prompt
    
    except Exception as e:
        print(f"Error generating Default Prompt: {e}")
        return None






def convert_date_str_to_date(date_str, business=None):
    # Get the business timezone if provided, otherwise use Chicago timezone as default
    timezone_str = 'America/Chicago'
    if business:
        try:
            timezone_str = business.timezone
        except:
            pass
    
    # Get current time in the business timezone
    business_time = datetime.now().astimezone(pytz.timezone(timezone_str))
    
    SYSTEM_PROMPT = f"""
    You are a helpful assistant that can convert any date and time format to a standardized datetime object.
    
    Current time in {timezone_str}: {business_time}

    Takes any human readable date string or any datetime format string and convert it to datetime object.
    Return only single datetime object in string format (YYYY-MM-DD HH:MM:SS).
    
    Important rules:
    - If no time is provided, use 00:00:00 as the default time
    - Handle both US (M/D/YYYY) and international (D/M/YYYY) date formats intelligently
    - Support natural language dates including ordinals (e.g., "7th of April, 2025")
    - Parse relative dates like "tomorrow", "next week", "in 3 days"
    - Always return in YYYY-MM-DD HH:MM:SS format in {timezone_str} timezone
    - Do not include any explanations, only return the formatted datetime

    example:
    Input: Tomorrow at 2 PM
    Output: 2025-03-12 14:00:00

    Input: Today at 10 AM
    Output: 2025-03-11 10:00:00

    Input: Next week monday at 3 PM
    Output: 2025-03-18 15:00:00

    Input: 13th mar at 10 am
    Output: 2025-03-13 10:00:00
    
    Input: 4/7/2025
    Output: 2025-04-07 00:00:00
    
    Input: 7th of April, 2025
    Output: 2025-04-07 00:00:00
    
    Input: 12-25-2025
    Output: 2025-12-25 00:00:00
    
    Input: April 7
    Output: 2025-04-07 00:00:00
    """
    
    formatted_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Date string: {date_str}"}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=formatted_messages,
        temperature=0.1,
        max_tokens=100
        )
    
    response_text = response.choices[0].message.content.strip()

    print(f"[UTIL] Converted {date_str} to datetime object: {response_text} in timezone {timezone_str}")

    return response_text


def format_messages_for_openai(messages, system_prompt):
    """Format chat messages for OpenAI API"""
    formatted_messages = [{"role": "system", "content": system_prompt}]
    
    for message in messages:
        if hasattr(message, 'role'):
            # Handle Messages objects
            role = message.role
            content = message.message
            
            # Convert tool messages to assistant messages
            if role == 'tool':
                # If it's a JSON string, leave it as is, otherwise stringify it
                if not isinstance(content, str) or (isinstance(content, str) and not content.startswith('{')):
                    content = f"Tool Response: {str(content)}"
                formatted_messages.append({
                    "role": "assistant",
                    "content": content
                })
            else:
                formatted_messages.append({"role": role, "content": content})
        elif isinstance(message, dict):
            # Handle dictionary messages
            role = message.get('role')
            content = message.get('content') or message.get('message')
            
            if role and content:
                # Convert tool messages to assistant messages
                if role == 'tool':
                    # If it's a JSON string, leave it as is, otherwise stringify it
                    if not isinstance(content, str) or (isinstance(content, str) and not content.startswith('{')):
                        content = f"Tool Response: {str(content)}"
                    formatted_messages.append({
                        "role": "assistant",
                        "content": content
                    })
                else:
                    formatted_messages.append({"role": role, "content": content})
    
    return formatted_messages


def get_chat_status(chat):
    """
    Use OpenAI to analyze a chat and determine its status
    """
    try:
        # Get chat messages directly from database
        from .models import Messages
        messages = Messages.objects.filter(chat=chat).order_by('createdAt')
        
        if not messages.exists():
            return "pending"
        
        # Format messages for OpenAI
        SYSTEM_PROMPT = """
        You are an AI assistant that analyzes conversations and returns their status using a single-word response.

        Instructions:
        Analyze the conversation and determine its current status.
        Respond with only one word from the predefined list below.
        Do not add any extra text, explanations, or formatting.
        Allowed Responses:
        pending → Conversation is ongoing, and not respondeded.
        booked → If the user has confirmed a booking no matter conversation is ongoing or not.
        not_interested → The user is not interested.
       
        Example Outputs:
        If the conversation is unresolved → pending
        If the user confirms a booking → booked
        If the user expresses disinterest → not_interested
        If booking is confirmed → booked
        
        Important Rules:
        ✅ Return only one word from the list.
        ❌ Do not generate full sentences, explanations, or additional text.
        """
        
        formatted_messages = format_messages_for_openai(messages, SYSTEM_PROMPT)

        
        # Call OpenAI API
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=formatted_messages
            )
            
            response_text = response.choices[0].message.content.strip().lower()
            
            # Validate the response is one of the expected values
            valid_statuses = ["pending", "booked", "not_interested"]
            if response_text not in valid_statuses:
                response_text = "pending"
                
            chat.status = response_text
            chat.save()
            return response_text
            
        except Exception as e:
            print(f"[UTIL] Error getting chat status from OpenAI: {str(e)}")
            print(traceback.format_exc())
            return "error"
            
    except Exception as e:
        print(f"[UTIL] Error in get_chat_status: {str(e)}")
        print(traceback.format_exc())
        return "error"
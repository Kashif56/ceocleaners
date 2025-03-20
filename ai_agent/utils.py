import google.generativeai as genai
from datetime import datetime
import pytz
from dotenv import load_dotenv
import os
from .views import OpenAIAgent
from openai import OpenAI
load_dotenv()


# Initialize Google Gemini AI
genai.configure(api_key=os.getenv('GEMENI_API'))
model = genai.GenerativeModel('gemini-2.0-flash')
# Change timezone to chicago
current_time = datetime.now().astimezone(pytz.timezone('America/Chicago'))

def convert_date_str_to_date(date_str):
    SYSTEM_PROMPT = f"""
    You are a helpful assistant that can convert a human readable date string to a datetime object.
    
    Current time: {current_time}

    Takes any human readable date string and convert it to datetime object
    Return only single datetime object in string format

    example:
    Input: Tomorrow at 2 PM
    Output: 2025-03-12 14:00:00

    Input: Today at 10 AM
    Output: 2025-03-11 10:00:00

    Input: Next week monday at 3 PM
    Output: 2025-03-18 15:00:00

    Input: 13th mar at 10 am
    Output: 2025-03-13 10:00:00
    """
    
    formatted_messages = [
        {"role": "model", "parts": [{"text": SYSTEM_PROMPT}]},
        {"role": "user", "parts": [{"text": f"Date string: {date_str}"}]}
    ]
    
    response = model.generate_content(
        formatted_messages,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=100,
            top_p=0.95,
            top_k=40,
        )
    )
    
    print(f"[DEBUG] String Date to DateTime - UTIL Function: {response.text}")
    return response.text



def get_chat_status(chat):
    messages = OpenAIAgent.get_chat_messages(chat.clientPhoneNumber)
    
    # Format messages for OpenAI without system prompt
    SYSTEM_PROMPT = """
    You are an AI assistant that analyzes conversations and returns their status using a single-word response.

    Instructions:
    Analyze the conversation and determine its current status.
    Respond with only one word from the predefined list below.
    Do not add any extra text, explanations, or formatting.
    Allowed Responses:
    pending → Conversation is ongoing, and not respondeded.
    booked → The user has confirmed a booking.
    not_interested → The user is not interested.
   
    Example Outputs:
    If the conversation is unresolved → pending
    If the user confirms a booking → booked
    If the user expresses disinterest → not_interested
    
    Important Rules:
    ✅ Return only one word from the list.
    ❌ Do not generate full sentences, explanations, or additional text.

"""
    formatted_messages = OpenAIAgent.format_messages_for_openai(messages, SYSTEM_PROMPT)
    
    # Call OpenAI API
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=formatted_messages
        )
        
        response_text = response.choices[0].message.content
        chat.status = response_text
        chat.save()
        print(f"[DEBUG] Chat status updated to: {response_text}")
        return response_text
    except Exception as e:
        print(f"[DEBUG] Error getting chat status: {e}")
        return "error"
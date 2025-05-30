from django.utils import timezone
from datetime import datetime, timedelta
from subscription.models import UsageTracker
from django.utils.timezone import make_aware, is_aware

class UsageService:
    """Service class for tracking and retrieving usage metrics."""
    
    @staticmethod
    def track_voice_call(business, duration_seconds=0):
        """
        Track a voice call usage.
        
        Args:
            business: The business making the call
            duration_seconds: Duration of the call in seconds
        """
        # Track call count
        UsageTracker.increment_metric(
            business=business,
            metric_name='voice_calls',
            increment_by=1
        )
        
        # Track call minutes (rounded up to nearest minute)
        minutes = (duration_seconds + 59) // 60  # Round up
        if minutes > 0:
            UsageTracker.increment_metric(
                business=business,
                metric_name='voice_minutes',
                increment_by=minutes
            )
        
        return True
    
    @staticmethod
    def track_sms_message(business, count=1):
        """
        Track SMS message usage.
        
        Args:
            business: The business sending the message
            count: Number of messages to track
        """
        UsageTracker.increment_metric(
            business=business,
            metric_name='sms_messages',
            increment_by=count
        )
        
        return True
    
    @staticmethod
    def get_business_usage(business, start_date=None, end_date=None):
        """
        Get usage metrics for a business within a date range.
        
        Args:
            business: The business to get metrics for
            start_date: Start date for metrics (default: first day of current month)
            end_date: End date for metrics (default: today)
        
        Returns:
            Dict with usage metrics
        """
        if not start_date:
            start_date = timezone.now().date().replace(day=1)
        if not end_date:
            end_date = timezone.now().date()
            
        return UsageTracker.get_usage_summary(
            business=business,
            start_date=start_date,
            end_date=end_date
        )
    
    @staticmethod
    def get_recent_activities(business, limit=10):
        """
        Get recent call and SMS activities for a business.
        
        Args:
            business: The business to get activities for
            limit: Maximum number of activities to return
            
        Returns:
            List of activity items with type, contact, status, etc.
        """
        import requests
        import json
        from django.conf import settings
        from retell_agent.models import RetellAgent
        from ai_agent.models import Messages, Chat
        from datetime import datetime
        
        activities = []
        
        # Get SMS messages - directly filter messages by business
        messages = Messages.objects.filter(
            chat__business=business,  # Filter messages by business directly
            role__in=['assistant', 'user']
        ).exclude(
            is_first_message=True
        ).select_related(
            'chat'  # Use select_related to optimize the query
        ).order_by(
            '-createdAt'
        )[:20]  # Get more messages initially for better mix
        
        # Process messages
        for message in messages:
            # Ensure timestamp is timezone-aware
            message_timestamp = message.createdAt
            if not is_aware(message_timestamp):
                message_timestamp = make_aware(message_timestamp)
            
            # Limit message preview to 20 characters
            preview = message.message[:20] + ('...' if len(message.message) > 20 else '')
            
            # Add message to activities
            activities.append({
                'type': 'sms',
                'contact': message.chat.clientPhoneNumber or f"WebChat: {message.chat.sessionKey}",
                'status': 'Sent' if message.role == 'assistant' else 'Received',
                'preview': preview,
                'agent': 'AI Assistant' if message.role == 'assistant' else 'Customer',
                'timestamp': message_timestamp,
                'chat_id': message.chat.id
            })
        
        # Get Retell calls
        try:
            # Get the Retell agent for this business
            agents = RetellAgent.objects.filter(business=business)
            
            if agents.exists():
                for agent in agents:
                    # Only proceed if we have an agent_id
                    if not agent.agent_id:
                        continue
                    
                    # Prepare the API request to Retell
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {settings.RETELL_API_KEY}'
                    }
                    
                    # Simplified payload with minimal filtering
                    payload = {
                        "filter_criteria": {
                            "agent_id": [agent.agent_id]
                        },
                        "sort_order": "descending",
                        "limit": 20
                    }
                    
                    try:
                        response = requests.post(
                            'https://api.retellai.com/v2/list-calls',
                            headers=headers,
                            json=payload,
                            timeout=5  # Reduced timeout for faster response
                        )
                        
                        if response.status_code == 200:
                            call_data = response.json()
                            
                            # Handle the case where the API returns a list instead of a dict with 'calls' key
                            calls = []
                            if isinstance(call_data, list):
                                calls = call_data
                            else:
                                calls = call_data.get('calls', [])
                            
                            for call in calls:
                                # Calculate call duration if timestamps are available
                                duration_seconds = 0
                                duration_text = "N/A"
                                
                                start_timestamp = call.get('start_timestamp')
                                end_timestamp = call.get('end_timestamp')
                                
                                if start_timestamp and end_timestamp:
                                    duration_seconds = (end_timestamp - start_timestamp) // 1000
                                    minutes = duration_seconds // 60
                                    seconds = duration_seconds % 60
                                    duration_text = f"{minutes}m {seconds}s"
                                
                                # Convert timestamp to datetime and ensure it's timezone-aware
                                call_time = timezone.now()  # Default to current time if no timestamp
                                if start_timestamp:
                                    # Create timezone-aware datetime
                                    naive_time = datetime.fromtimestamp(start_timestamp / 1000)
                                    call_time = make_aware(naive_time)
                                
                                # Get the phone number with proper formatting
                                to_number = call.get('to_number', 'Unknown')
                                if to_number and not to_number.startswith('+'):
                                    to_number = f"+{to_number}"
                                
                                # Determine correct status based on call data
                                status = call.get('call_status', 'Unknown')
                               
                                activities.append({
                                    'type': 'voice',
                                    'contact': to_number,
                                    'status': status,
                                    'duration': duration_text,
                                    'duration_seconds': duration_seconds,
                                    'agent': agent.agent_name,
                                    'timestamp': call_time,
                                    'call_id': call.get('call_id')
                                })
                    except requests.exceptions.RequestException:
                        # Silently handle request errors to improve performance
                        pass
        except Exception:
            # Silently handle exceptions to improve performance
            pass
        
        # Ensure all timestamps are timezone-aware before sorting
        for activity in activities:
            if not is_aware(activity['timestamp']):
                activity['timestamp'] = make_aware(activity['timestamp'])
        
        # Sort all activities by timestamp (newest first)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Ensure we have a mix of both types in the final result
        if len(activities) > limit:
            # Get voice and SMS activities separately
            voice_activities = [a for a in activities if a['type'] == 'voice']
            sms_activities = [a for a in activities if a['type'] == 'sms']
            
            # If we have both types, ensure we include some of each
            if voice_activities and sms_activities:
                # Aim for a balanced mix, but respect the original sorting
                result = []
                voice_count = min(limit // 2, len(voice_activities))
                sms_count = min(limit - voice_count, len(sms_activities))
                
                # If we couldn't get enough SMS, add more voice
                if sms_count < limit - voice_count:
                    voice_count = min(limit - sms_count, len(voice_activities))
                
                # Add the selected activities
                result.extend(voice_activities[:voice_count])
                result.extend(sms_activities[:sms_count])
                
                # Re-sort the combined result
                result.sort(key=lambda x: x['timestamp'], reverse=True)
                
                return result
        
        # Return only the requested number of activities
        return activities[:limit]
    
    @staticmethod
    def check_usage_limits(business):
        """
        Check if a business has exceeded its usage limits.
        
        Args:
            business: The business to check
        
        Returns:
            Dict with usage status and limit information
        """
        # Get current subscription
        try:
            from subscription.models import BusinessSubscription
            subscription = BusinessSubscription.objects.filter(
                business=business,
                is_active=True
            ).latest('created_at')
            
            if not subscription or not subscription.is_subscription_active():
                return {
                    'has_active_subscription': False,
                    'limits_exceeded': True,
                    'message': 'No active subscription found.'
                }
            
            # Get current usage
            current_usage = UsageTracker.get_usage_summary(business=business)
            
            # Check limits
            voice_minutes_exceeded = current_usage['voice_minutes'] > subscription.plan.voice_minutes
            voice_calls_exceeded = current_usage['voice_calls'] > subscription.plan.voice_calls
            sms_messages_exceeded = current_usage['sms_messages'] > subscription.plan.sms_messages
            
            limits_exceeded = voice_minutes_exceeded or voice_calls_exceeded or sms_messages_exceeded
            
            return {
                'has_active_subscription': True,
                'limits_exceeded': limits_exceeded,
                'voice_minutes': {
                    'used': current_usage['voice_minutes'],
                    'limit': subscription.plan.voice_minutes,
                    'exceeded': voice_minutes_exceeded
                },
                'voice_calls': {
                    'used': current_usage['voice_calls'],
                    'limit': subscription.plan.voice_calls,
                    'exceeded': voice_calls_exceeded
                },
                'sms_messages': {
                    'used': current_usage['sms_messages'],
                    'limit': subscription.plan.sms_messages,
                    'exceeded': sms_messages_exceeded
                }
            }
            
        except BusinessSubscription.DoesNotExist:
            return {
                'has_active_subscription': False,
                'limits_exceeded': True,
                'message': 'No active subscription found.'
            } 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from django.template.defaultfilters import register
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import PlatformIntegration, DataMapping, IntegrationLog
from .utils import log_integration_activity
from accounts.models import Business, ApiCredential
from bookings.models import Booking
import json
from datetime import datetime, timedelta
from decimal import Decimal
from automation.webhooks import send_booking_data
import requests
from django.conf import settings
# Create your views here.

@login_required
@ensure_csrf_cookie
def integration_list(request):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')

    integrations = PlatformIntegration.objects.filter(business=business)
    return render(request, 'integrations/integration_list.html', {
        'integrations': integrations
    })

@login_required
def add_integration(request):
    if request.method == 'POST':
        name = request.POST.get('serviceName')
        platform_type = request.POST.get('platformType')
        
        integration_data = {
            'name': name,
            'platform_type': platform_type,
            'business': request.user.business_set.first(),
            'is_active': True
        }

        # Get headers from form if provided
        headers_json = request.POST.get('headers_json', '{}')
        try:
            headers = json.loads(headers_json)
        except json.JSONDecodeError:
            headers = {}
            
        if platform_type == 'direct_api':
            integration_data.update({
                'base_url': request.POST.get('api_url'),
                'headers': headers
            })
        else:  # workflow platform
            integration_data.update({
                'webhook_url': request.POST.get('webhook_url'),
                'headers': headers
            })

        # Create new integration
        integration = PlatformIntegration.objects.create(**integration_data)

      
        messages.success(request, 'Integration added successfully!')
        if platform_type == 'direct_api':
            return redirect('integration_mapping', platform_id=integration.id)
        return redirect('integration_list')

    context = {
        'platform_types': dict(PlatformIntegration.PLATFORM_TYPE_CHOICES),
        'integration': None
    }
    
    return render(request, 'integrations/add_integration.html', context)

@login_required
def integration_mapping(request, platform_id):
    platform = get_object_or_404(PlatformIntegration, id=platform_id, business=request.user.business_set.first())
    
    # If it's a workflow platform, redirect to integration list
    if platform.platform_type == 'workflow':
        messages.info(request, 'Workflow platforms do not require field mapping.')
        return redirect('integration_list')
        
    mappings = DataMapping.objects.filter(platform=platform)
    
    if request.method == 'POST':
        data = json.loads(request.body)
        mappings_data = data.get('mappings', [])
        
        # Delete existing mappings
        DataMapping.objects.filter(platform=platform).delete()
        
        # Create new mappings
        for mapping_data in mappings_data:
            DataMapping.objects.create(
                platform=platform,
                source_field=mapping_data['source_field'],
                target_field=mapping_data['target_field'],
                parent_path=mapping_data.get('parent_path'),
                field_type=mapping_data.get('field_type', 'string'),
                default_value=mapping_data.get('default_value', ''),
                is_required=mapping_data.get('is_required', False)
            )
        
        return JsonResponse({'status': 'success'})

    # Get all available fields from Booking model
    booking_fields = []
    for field in Booking._meta.get_fields():
        if not field.is_relation and not field.auto_created:
            booking_fields.append((field.name, field.verbose_name or field.name.replace('_', ' ').title()))

    field_types = [
        ('string', 'Text'),
        ('number', 'Number'),
        ('boolean', 'True/False'),
        ('date', 'Date'),
        ('time', 'Time'),
        ('datetime', 'Date & Time'),
        ('array', 'Array/List'),
        ('object', 'Object')
    ]

    context = {
        'platform': platform,
        'mappings': mappings,
        'booking_fields': booking_fields,
        'field_types': field_types
    }

    return render(request, 'integrations/mapping.html', context)

@login_required
def preview_mapping(request, platform_id):
    platform = get_object_or_404(PlatformIntegration, id=platform_id, business=request.user.business_set.first())
    mappings = DataMapping.objects.filter(platform=platform)
    
    # Get a sample booking
    sample_booking = Booking.objects.filter(business=request.user.business_set.first()).first()
    
    if not sample_booking:
        # Create a dummy booking for preview if none exists
        sample_booking = Booking(
            firstName="John",
            lastName="Doe",
            email="john@example.com",
            phoneNumber="123-456-7890",
            address1="123 Main St",
            city="Sample City",
            stateOrProvince="State",
            zipCode="12345",
            bedrooms=3,
            bathrooms=2,
            serviceType="standard",
            cleaningDate="2025-03-01",
            totalPrice="150.00"
        )

    # Prepare sample booking data
    sample_data = {
        'firstName': sample_booking.firstName,
        'lastName': sample_booking.lastName,
        'email': sample_booking.email,
        'phoneNumber': sample_booking.phoneNumber,
        'address1': sample_booking.address1,
        'city': sample_booking.city,
        'stateOrProvince': sample_booking.stateOrProvince,
        'zipCode': sample_booking.zipCode,
        'bedrooms': sample_booking.bedrooms,
        'bathrooms': sample_booking.bathrooms,
        'serviceType': sample_booking.serviceType,
        'cleaningDate': sample_booking.cleaningDate,
        'totalPrice': sample_booking.totalPrice
    }

    # Generate mapped data
    mapped_data = {}
    required_fields = set()
    
    # Group mappings by type (flat vs nested)
    grouped_mappings = {
        'Flat': [],
        'Nested': []
    }
    
    for mapping in mappings:
        value = getattr(sample_booking, mapping.source_field, mapping.default_value)
        
        # Track required fields
        if mapping.is_required:
            required_fields.add(mapping.source_field)
        
        # Handle nested paths
        if mapping.parent_path:
            path_parts = mapping.parent_path.split('.')
            current_dict = mapped_data
            
            # Create nested structure
            for part in path_parts:
                if part not in current_dict:
                    current_dict[part] = {}
                current_dict = current_dict[part]
            
            current_dict[mapping.target_field] = value
            grouped_mappings['Nested'].append(mapping)
        else:
            mapped_data[mapping.target_field] = value
            grouped_mappings['Flat'].append(mapping)

    # Remove empty groups
    grouped_mappings = {k: v for k, v in grouped_mappings.items() if v}

    context = {
        'platform': platform,
        'mapped_data': mapped_data,
        'sample_booking': sample_data,
        'grouped_mappings': grouped_mappings,
        'required_fields': required_fields
    }

    return render(request, 'integrations/preview_mapping.html', context)

@login_required
@require_POST
def test_integration(request, platform_id):
    """Test an integration by sending sample data"""
    try:
        integration = get_object_or_404(
            PlatformIntegration, 
            id=platform_id, 
            business=request.user.business_set.first()
        )

        # Create test data that matches Booking model structure
        test_data = {
            "firstName": "Test",
            "lastName": "User",
            "email": "test@example.com",
            "phoneNumber": "+1234567890",
            "address1": "123 Test St",
            "address2": "Apt 4B",
            "city": "Test City",
            "stateOrProvince": "Test State",
            "zipCode": "12345",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFeet": 2000,
            "serviceType": "Deep Clean",
            "cleaningDate": datetime.now() + timedelta(days=7),
            "startTime": datetime.now(),
            "endTime": datetime.now() + timedelta(hours=1),
            "totalPrice": "299.99",
            "tax": "24.99",
            "addonDishes": True,
            "addonLaundryLoads": 2,
            "addonWindowCleaning": True,
            "addonPetsCleaning": False,
            "addonFridgeCleaning": True,
            "addonOvenCleaning": True,
            "addonBaseboard": True,
            "addonBlinds": False,
            "addonGreenCleaning": True,
            "addonCabinetsCleaning": True,
            "addonPatioSweeping": False,
            "addonGarageSweeping": False
        }

        # Send test data only to this specific integration
        test_results = send_booking_data_to_integration(test_data, integration)
        
        if test_results.get('success', []):
            return JsonResponse({
                'success': True,
                'message': 'Test data sent successfully!',
                'response': test_results['success'][0]  # Get the first success response
            })
        else:
            error_msg = test_results.get('failed', [{}])[0].get('error', 'Unknown error occurred')
            return JsonResponse({
                'success': False,
                'message': f'Failed to send test data: {error_msg}'
            }, status=400)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print("Test Integration Error:", error_details)  # Log the full error
        return JsonResponse({
            'success': False,
            'message': f'Error testing integration: {str(e)}'
        }, status=500)

def send_booking_data_to_integration(booking_data, integration):
    """Send booking data to a specific integration"""
    try:
        results = {
            'success': [],
            'failed': []
        }

        if integration.platform_type == 'workflow':
            # Convert datetime to string format
            cleaning_date = booking_data["cleaningDate"].date().isoformat()
            cleaning_time = booking_data["startTime"].strftime("%H:%M:%S")
            end_time = (booking_data["startTime"] + timedelta(minutes=60)).strftime("%H:%M:%S")

            # For workflow platforms, use the default payload structure
            payload = {
                "firstName": booking_data["firstName"],
                "lastName": booking_data["lastName"],
                "email": booking_data["email"],
                "phoneNumber": booking_data["phoneNumber"],
                "address1": booking_data["address1"],
                "address2": booking_data["address2"],
                "city": booking_data["city"],
                "stateOrProvince": booking_data["stateOrProvince"],
                "zipCode": booking_data["zipCode"],
                "bedrooms": booking_data["bedrooms"],
                "bathrooms": booking_data["bathrooms"],
                "squareFeet": booking_data["squareFeet"],
                "serviceType": booking_data["serviceType"],
                "cleaningDate": cleaning_date,
                "startTime": cleaning_time,
                "endTime": end_time,
                "totalPrice": float(booking_data["totalPrice"]),
                "tax": float(booking_data["tax"] or 0),
                "addonDishes": booking_data["addonDishes"],
                "addonLaundryLoads": booking_data["addonLaundryLoads"],
                "addonWindowCleaning": booking_data["addonWindowCleaning"],
                "addonPetsCleaning": booking_data["addonPetsCleaning"],
                "addonFridgeCleaning": booking_data["addonFridgeCleaning"],
                "addonOvenCleaning": booking_data["addonOvenCleaning"],
                "addonBaseboard": booking_data["addonBaseboard"],
                "addonBlinds": booking_data["addonBlinds"],
                "addonGreenCleaning": booking_data["addonGreenCleaning"],
                "addonCabinetsCleaning": booking_data["addonCabinetsCleaning"],
                "addonPatioSweeping": booking_data["addonPatioSweeping"],
                "addonGarageSweeping": booking_data["addonGarageSweeping"]
            }
            
            # Prepare headers
            headers = {"Content-Type": "application/json"}
            
            # Add custom headers from integration if available
            if integration.headers:
                headers.update(integration.headers)
                
            response = requests.post(
                integration.webhook_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code in [200, 201]:
                log_integration_activity(
                    platform=integration,
                    status='success',
                    request_data=payload,
                    response_data=response.json() if response.text else None
                )
            else:
                log_integration_activity(
                    platform=integration,
                    status='failed',
                    request_data=payload,
                    error_message=response.text
                )
            
        else:  # direct_api
            from automation.webhooks import create_mapped_payload
            payload = create_mapped_payload(booking_data, integration)
            
            
            headers = {"Content-Type": "application/json"}
            
            # Add custom headers from integration if available
            if integration.headers:
                headers.update(integration.headers)
            
            print("Payload:", payload)
            print("Headers:", headers)
            
            response = requests.post(
                integration.base_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code in [200, 201]:
                log_integration_activity(
                    platform=integration,
                    status='success',
                    request_data=payload,
                    response_data=response.json() if response.text else None
                )
            else:
                log_integration_activity(
                    platform=integration,
                    status='failed',
                    request_data=payload,
                    error_message=response.text
                )
        results['success'].append({
            'name': integration.name,
            'response': response.text,
            'status_code': response.status_code
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print("Test Integration Error:", error_details)  # Log the full error
        # Log failed integration
        log_integration_activity(
            platform=integration,
            status='failed',
            request_data=payload if 'payload' in locals() else {},
            error_message=str(e)
        )
        
        results['failed'].append({
            'name': integration.name,
            'error': str(e)
        })
    
    return results

@login_required
def edit_integration(request, platform_id):
    platform = get_object_or_404(PlatformIntegration, id=platform_id, business=request.user.business_set.first())
    
    if request.method == 'POST':
        name = request.POST.get('serviceName')
        platform_type = request.POST.get('platformType')
        is_active = request.POST.get('is_active') == 'on'
        
        # Update basic fields
        platform.name = name
        platform.platform_type = platform_type
        platform.is_active = is_active
        
        # Get headers from form if provided
        headers_json = request.POST.get('headers_json', '{}')
        try:
            headers = json.loads(headers_json)
        except json.JSONDecodeError:
            headers = {}
            
        # Update headers
        platform.headers = headers
        
        # Update type-specific fields
        if platform_type == 'direct_api':
            platform.base_url = request.POST.get('api_url')
            platform.auth_type = 'token'  # Default to token auth
            
            # Only update the token if a new one is provided
            api_key = request.POST.get('api_key')
            if api_key:
                platform.auth_data = {'token': api_key}
                
            # Clear webhook URL if switching from workflow to direct API
            platform.webhook_url = ''
        else:  # workflow platform
            platform.webhook_url = request.POST.get('webhook_url')
            platform.auth_type = 'none'
            
            # Clear API-specific fields if switching from direct API to workflow
            platform.base_url = ''
            platform.auth_data = {}
        
        platform.save()
        messages.success(request, 'Integration updated successfully!')
        
        if platform_type == 'direct_api':
            return redirect('integration_mapping', platform_id=platform.id)
        return redirect('integration_list')
       
    # Get choices from model
    platform_types = dict(PlatformIntegration.PLATFORM_TYPE_CHOICES)
    
    return render(request, 'integrations/edit_integration.html', {
        'integration': platform,
        'platform_types': platform_types,
    })

@login_required
def delete_integration(request, platform_id):
    platform = get_object_or_404(PlatformIntegration, id=platform_id, business=request.user.business_set.first())
    if request.method == 'POST':
        platform.delete()
        messages.success(request, 'Integration deleted successfully!')
        return redirect('integration_list')
    
    return render(request, 'integrations/delete_confirmation.html', {
        'platform': platform
    })

@login_required
def save_field_mappings(request, integration_id):
    if request.method == 'POST':
        try:
            integration = get_object_or_404(PlatformIntegration, id=integration_id)
            data = json.loads(request.body)
            mappings = data.get('mappings', [])

            # Delete existing mappings
            DataMapping.objects.filter(platform=integration).delete()

            # Create new mappings
            for mapping in mappings:
                DataMapping.objects.create(
                    platform=integration,
                    source_field=mapping['source_field'],
                    target_field=mapping['target_field']
                )

            return JsonResponse({
                'success': True,
                'message': 'Mappings saved successfully',
                'redirect_url': reverse('integration_list')
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    })


#===========================================
#                   Retell
#===========================================

@login_required
def retell_settings(request):
    """
    Display available Retell API functions and their documentation
    """
    business = Business.objects.get(user=request.user)
    secretKey = ApiCredential.objects.get(business=business).secretKey
    if not business.useCall:
        messages.info(request, "Voice AI calling features are not enabled for your account.")
        # Redirect back to the referring page or integration list as fallback
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('home')
    
    BASE_URL = settings.BASE_URL
    
    bookAppointmentURL = f"{BASE_URL}/api/create-booking/"
    check_availability = f"{BASE_URL}/api/availability/{secretKey}/"
    send_commercial_link = f"{BASE_URL}/api/send-commercial-form-link/"

    context = {
        'book_appointment_url': bookAppointmentURL,
        'check_availability': check_availability,
        'send_commercial_link': send_commercial_link
    }
    
    return render(request, 'integrations/retell_settings.html', context)

@login_required
def integration_logs(request, platform_id=None):
    """View integration logs for all integrations or a specific one"""
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
        
    # Get query parameters for filtering
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base query - filter by business
    if platform_id:
        # For a specific integration
        platform = get_object_or_404(PlatformIntegration, id=platform_id, business=business)
        logs_query = IntegrationLog.objects.filter(platform=platform)
        # Set the title accordingly
        title = f"Integration Logs: {platform.name}"
    else:
        # For all integrations of this business
        platforms = PlatformIntegration.objects.filter(business=business)
        logs_query = IntegrationLog.objects.filter(platform__in=platforms)
        title = "All Integration Logs"
    
    # Apply filters if provided
    if status_filter:
        logs_query = logs_query.filter(status=status_filter)
        
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            logs_query = logs_query.filter(created_at__gte=date_from_obj)
        except ValueError:
            pass  # Invalid date format
            
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the end date
            date_to_obj = date_to_obj + timedelta(days=1)
            logs_query = logs_query.filter(created_at__lt=date_to_obj)
        except ValueError:
            pass  # Invalid date format
    
    # Get logs with pagination (20 logs per page)
    paginator = Paginator(logs_query.order_by('-created_at'), 20)
    page = request.GET.get('page')
    try:
        logs = paginator.page(page)
    except PageNotAnInteger:
        logs = paginator.page(1)
    except EmptyPage:
        logs = paginator.page(paginator.num_pages)
    
    # Get all integrations for the filter dropdown
    integrations = PlatformIntegration.objects.filter(business=business)
    
    # Get stats
    total_logs = logs_query.count()
    success_logs = logs_query.filter(status='success').count()
    failed_logs = logs_query.filter(status='failed').count()
    pending_logs = logs_query.filter(status='pending').count()
    
    context = {
        'logs': logs,
        'integrations': integrations,
        'platform_id': platform_id,
        'status_filter': status_filter, 
        'date_from': date_from,
        'date_to': date_to,
        'title': title,
        'status_choices': dict(IntegrationLog.STATUS_CHOICES),
        'paginator': paginator,
        'total_logs': total_logs,
        'success_logs': success_logs,
        'failed_logs': failed_logs,
        'pending_logs': pending_logs
    }
    
    return render(request, 'integrations/integration_logs.html', context)

# Template filter for pretty printing JSON data
@register.filter
def pprint(data):
    if isinstance(data, dict) or isinstance(data, list):
        return json.dumps(data, indent=2)
    return data

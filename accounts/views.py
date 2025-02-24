from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from accounts.models import Business, BusinessSettings, BookingIntegration, ApiCredential, CustomAddons
import random
from django.http import JsonResponse


def SignupPage(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        
        if password1 == password2:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('accounts:signup')

            user = User.objects.create_user(username=username, password=password1)
            messages.success(request, 'Account created successfully!')
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Passwords do not match.')
            return redirect('accounts:signup')
    
    return render(request, 'accounts/signup.html')


def loginPage(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Logged in successfully!')
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')


def logoutUser(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    business = request.user.business_set.first()
    
    if not business:
        messages.warning(request, 'Please register your business first.')
        return redirect('accounts:register_business')
    
    # Get related models
    business_settings = business.settings
    api_credentials = business.apicredential
    booking_integrations = business.bookingIntegrations.all()
    
    context = {
        'business': business,
        'settings': business_settings,
        'credentials': api_credentials,
        'integrations': booking_integrations,
    }
    
    return render(request, 'accounts/profile.html', context)


@login_required
def update_profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        user.save()
        
        messages.success(request, 'Your profile has been updated successfully!')
        return redirect('accounts:profile')
    
    return redirect('accounts:profile')


@login_required
def update_credentials(request):
    if request.method == 'POST':
        credentials, created = ApiCredential.objects.get_or_create(user=request.user)
        
        # Update credentials fields
        credentials.apiKey = request.POST.get('apiKey', '')
        credentials.auth_token = request.POST.get('auth_token', '')
        credentials.twilio_number = request.POST.get('twilio_number', '')
        credentials.twilio_whatsapp_number = request.POST.get('twilio_whatsapp_number', '')
        credentials.save()
        
        messages.success(request, 'Your API credentials have been updated successfully!')
        return redirect('accounts:profile')
    
    return redirect('accounts:profile')


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Update the session to prevent the user from being logged out
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('accounts:profile')
        else:
            messages.error(request, 'Please correct the errors below.')
            return redirect('accounts:profile')
    
    return redirect('accounts:profile')


@login_required
def register_business(request):
    # Check if user already has a business
    if request.user.business_set.exists():
        messages.warning(request, 'You already have a registered business.')
        return redirect('accounts:profile')
    
    if request.method == 'POST':
        businessName = request.POST.get('businessName')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        
        # Validate required fields
        if not all([businessName, phone, address]):
            messages.error(request, 'All fields are required.')
            return render(request, 'accounts/register_business.html')
        
        try:
            # Create business
            business = Business.objects.create(
                user=request.user,
                businessName=businessName,
                phone=phone,
                address=address
            )
            
            # Create default settings for the business
            BusinessSettings.objects.create(business=business)
            
            # Create API credentials
            ApiCredential.objects.create(
                business=business,
            )
            
            messages.success(request, 'Business registered successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error registering business: {str(e)}')
            return render(request, 'accounts/register_business.html')
    
    return render(request, 'accounts/register_business.html')


@login_required
def edit_business(request):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    if request.method == 'POST':
        businessName = request.POST.get('businessName')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        
        if not all([businessName, phone, address]):
            messages.error(request, 'All fields are required.')
            return render(request, 'accounts/edit_business.html', {'business': business})
        
        try:
            business.businessName = businessName
            business.phone = phone
            business.address = address
            business.save()
            
            messages.success(request, 'Business information updated successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error updating business: {str(e)}')
    
    return render(request, 'accounts/edit_business.html', {'business': business})


@login_required
def edit_business_settings(request):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    settings = business.settings
    
    if request.method == 'POST':
        try:
            # Base Pricing
            settings.bedroomPrice = request.POST.get('bedroomPrice', 0)
            settings.bathroomPrice = request.POST.get('bathroomPrice', 0)
            settings.depositFee = request.POST.get('depositFee', 0)
            settings.taxPercent = request.POST.get('taxPercent', 0)
            
            # Square Feet Multipliers
            settings.sqftMultiplierStandard = request.POST.get('sqftMultiplierStandard', 0)
            settings.sqftMultiplierDeep = request.POST.get('sqftMultiplierDeep', 0)
            settings.sqftMultiplierMoveinout = request.POST.get('sqftMultiplierMoveinout', 0)
            settings.sqftMultiplierAirbnb = request.POST.get('sqftMultiplierAirbnb', 0)
            
            # Add-on Prices
            settings.addonPriceDishes = request.POST.get('addonPriceDishes', 0)
            settings.addonPriceLaundry = request.POST.get('addonPriceLaundry', 0)
            settings.addonPriceWindow = request.POST.get('addonPriceWindow', 0)
            settings.addonPricePets = request.POST.get('addonPricePets', 0)
            settings.addonPriceFridge = request.POST.get('addonPriceFridge', 0)
            settings.addonPriceOven = request.POST.get('addonPriceOven', 0)
            settings.addonPriceBaseboard = request.POST.get('addonPriceBaseboard', 0)
            settings.addonPriceBlinds = request.POST.get('addonPriceBlinds', 0)
            settings.addonPriceGreen = request.POST.get('addonPriceGreen', 0)
            settings.addonPriceCabinets = request.POST.get('addonPriceCabinets', 0)
            settings.addonPricePatio = request.POST.get('addonPricePatio', 0)
            settings.addonPriceGarage = request.POST.get('addonPriceGarage', 0)
            
            settings.save()
            messages.success(request, 'Business settings updated successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    return render(request, 'accounts/edit_business_settings.html', {'settings': settings})


@login_required
def edit_credentials(request):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    credentials = business.apicredential
    
    if request.method == 'POST':
        try:
            credentials.retellAPIKey = request.POST.get('retellAPIKey')
            credentials.retellWebhookURL = request.POST.get('retellWebhookURL')
            credentials.voiceAgentNumber = request.POST.get('voiceAgentNumber')
            credentials.gmail_host_user = request.POST.get('gmail_host_user')
            credentials.gmail_host_password = request.POST.get('gmail_host_password')
            credentials.save()
            
            messages.success(request, 'API credentials updated successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error updating credentials: {str(e)}')
    
    return render(request, 'accounts/edit_credentials.html', {'credentials': credentials})


@login_required
def add_integration(request):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    if request.method == 'POST':
        try:
            integration = BookingIntegration(
                business=business,
                serviceName=request.POST.get('serviceName'),
                apiKey=request.POST.get('apiKey'),
                webhookUrl=request.POST.get('webhookUrl')
            )
            integration.save()

            business.bookingIntegrations.add(integration)
            
            messages.success(request, 'Integration added successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error adding integration: {str(e)}')
    
    return render(request, 'accounts/add_integration.html')


@login_required
def edit_integration(request, pk):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    integration = get_object_or_404(BookingIntegration, pk=pk, business=business)
    
    if request.method == 'POST':
        try:
            integration.serviceName = request.POST.get('serviceName')
            integration.apiKey = request.POST.get('apiKey')
            integration.webhookUrl = request.POST.get('webhookUrl')
            integration.save()
            
            messages.success(request, 'Integration updated successfully!')
            return redirect('accounts:profile')
            
        except Exception as e:
            messages.error(request, f'Error updating integration: {str(e)}')
    
    return render(request, 'accounts/edit_integration.html', {'integration': integration})


@login_required
def delete_integration(request, pk):
    business = request.user.business_set.first()
    if not business:
        return redirect('accounts:register_business')
    
    integration = get_object_or_404(BookingIntegration, pk=pk, business=business)
    
    try:
        integration.delete()
        messages.success(request, 'Integration deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting integration: {str(e)}')
    
    return redirect('accounts:profile')


@login_required
def generate_secret_key(request):
    business = request.user.business_set.first()
    if not business:
        messages.error(request, 'No business found.')
        return redirect('accounts:register_business')
    
    try:
        credentials = business.apicredential
        credentials.secretKey = f"sk_{business.businessId}_{random.randint(100000, 999999)}"
        credentials.save()
        messages.success(request, 'Secret key generated successfully!')
    except Exception as e:
        messages.error(request, f'Error generating secret key: {str(e)}')
    
    return redirect('accounts:profile')


@login_required
def add_custom_addon(request):
    if request.method == 'POST':
        business = request.user.business
        addon_name = request.POST.get('addonName')
        addon_price = request.POST.get('addonPrice', 0)
        
        CustomAddons.objects.create(
            business=business,
            addonName=addon_name,
            addonPrice=addon_price
        )
        
        messages.success(request, 'Custom addon added successfully!')
        return redirect('accounts:edit_business_settings')
    
    return redirect('accounts:edit_business_settings')


@login_required
def edit_custom_addon(request, addon_id):
    try:
        addon = CustomAddons.objects.get(id=addon_id, business=request.user.business)
        
        if request.method == 'POST':
            addon.addonName = request.POST.get('addonName')
            addon.addonPrice = request.POST.get('addonPrice', addon.addonPrice)
            addon.save()
            
            messages.success(request, 'Custom addon updated successfully!')
            return JsonResponse({'status': 'success'})
            
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
        
    except CustomAddons.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Addon not found'}, status=404)


@login_required
def delete_custom_addon(request, addon_id):
    try:
        addon = CustomAddons.objects.get(id=addon_id, business=request.user.business)
        addon.delete()
        messages.success(request, 'Custom addon deleted successfully!')
        return JsonResponse({'status': 'success'})
    except CustomAddons.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Addon not found'}, status=404)
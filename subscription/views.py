from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
from django.db import models
import json
import uuid
from square.client import Client

from .models import SubscriptionPlan, BusinessSubscription, BillingHistory, Feature, Coupon, CouponUsage, UsageTracker, SetupFee
from saas.models import PlatformSettings
from accounts.models import Business
from usage_analytics.services.usage_service import UsageService

@login_required
def subscription_management(request):
    """View for managing subscriptions."""
    business = request.user.business_set.first()
    
    # Get current subscription
    try:
        subscription = business.active_subscription()
        payment_method = subscription.square_customer_id is not None if subscription else False
        
        # Get next plan information if available
        next_plan = None
        if subscription and subscription.next_plan_id:
            try:
                next_plan = SubscriptionPlan.objects.get(id=subscription.next_plan_id)
            except SubscriptionPlan.DoesNotExist:
                pass
    except BusinessSubscription.DoesNotExist:
        subscription = None
        payment_method = False
        next_plan = None
    
    # Get all available plans (exclude invite-only plans)
    plans = SubscriptionPlan.objects.filter(is_active=True, is_invite_only=False).order_by('sort_order', 'price').exclude(plan_tier='trial')


   
    trial_plan = SubscriptionPlan.objects.filter(is_active=True, plan_tier='trial', is_invite_only=False).first()
    is_eligible_for_trial = False if BusinessSubscription.objects.filter(business=business, plan=trial_plan).exists() else True
    
    # Get usage summary for current month
    if subscription:
        usage_summary = UsageTracker.get_usage_summary(
            business=business,
            start_date=subscription.start_date,
            end_date=subscription.end_date
        )
    else:
        usage_summary = None
 
    
    # Get recent billing history
    billing_history = BillingHistory.objects.filter(
        business=business
    ).order_by('-billing_date')[:5]
    
    # Get card details from Square if available
    card_details = None
    customer_details = None
    if business.square_card_id and business.square_customer_id:
        try:
            # Initialize Square client
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Retrieve the card details
            card_result = square_client.cards.retrieve_card(
                card_id=business.square_card_id
            )
            
            if card_result.is_success():
                card = card_result.body.get('card', {})
                card_details = {
                    'last4': card.get('last_4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                    'card_brand': card.get('card_brand')
                }
                
            # Retrieve the customer details
            customer_result = square_client.customers.retrieve_customer(
                customer_id=business.square_customer_id
            )
            
            if customer_result.is_success():
                customer = customer_result.body.get('customer', {})
                created_at = datetime.strptime(customer.get('created_at'), '%Y-%m-%dT%H:%M:%S.%f%z')

            
                customer_details = {
                    'given_name': customer.get('given_name', ''),
                    'family_name': customer.get('family_name', ''),
                    'email': customer.get('email_address', ''),
                    'phone': customer.get('phone_number', ''),
                    'created_at': created_at
                }
        except Exception as e:
            # Log the error but don't crash
            print(f"Error retrieving card or customer details: {e}")
    
    context = {
        'subscription': subscription,
        'plans': plans,
        'trial_plan': trial_plan,
        'is_eligible_for_trial': is_eligible_for_trial,
        'usage_summary': usage_summary,
        'billing_history': billing_history,
        'next_plan': next_plan,
        'payment_method': payment_method,
        'business': business,
        'card_details': card_details,
        'customer_details': customer_details,
        'active_page': 'subscription',
        'title': 'Subscription Management'
    }
    
    return render(request, 'usage_analytics/subscription.html', context)

@login_required
def billing_history(request):
    """View for billing history."""
    business = request.user.business_set.first()
    
    # Get all billing records
    billing_records = BillingHistory.objects.filter(
        business=business
    ).order_by('-billing_date')
    
    # Calculate total billed for the current year
    current_year = timezone.now().year
    start_of_year = datetime(current_year, 1, 1, tzinfo=timezone.get_current_timezone())
    total_billed = BillingHistory.objects.filter(
        business=business,
        billing_date__gte=start_of_year,
        status='paid'
    ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    # Get last payment
    last_payment = BillingHistory.objects.filter(
        business=business,
        status='paid'
    ).order_by('-billing_date').first()
    
    # Get current subscription for next billing info
    subscription = None
    next_billing = {'date': None, 'amount': 0}
    current_balance = 0.00
    try:
        subscription = business.active_subscription()
    except BusinessSubscription.DoesNotExist:
        subscription = None

    next_plan_price = 0
    if subscription:
        try:
            next_plan_price = subscription.plan.price if subscription.plan else 0
        except Exception:
            next_plan_price = 0
        if subscription.next_plan_id:
            try:
                next_plan = SubscriptionPlan.objects.get(id=subscription.next_plan_id)
                next_plan_price = next_plan.price
            except SubscriptionPlan.DoesNotExist:
                pass
        next_billing = {
            'date': getattr(subscription, 'next_billing_date', None) or getattr(subscription, 'end_date', None),
            'amount': next_plan_price
        }
        if getattr(subscription, 'status', None) == 'past_due':
            current_balance = float(next_plan_price)
    else:
        next_billing = {'date': None, 'amount': 0}
        current_balance = 0.00

    
    # Get payment method info from Square
    payment_method = None
    # Fetch actual card details from Square if available
    if business.square_card_id and business.square_customer_id:
        try:
            # Initialize Square client
            from square.client import Client
            from django.conf import settings
            
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Retrieve the card details
            card_result = square_client.cards.retrieve_card(
                card_id=business.square_card_id
            )
            
            if card_result.is_success():
                card = card_result.body.get('card', {})
                payment_method = {
                    'last4': card.get('last_4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                    'card_brand': card.get('card_brand')
                }
        except Exception as e:
            # Log the error but don't crash
            print(f"Error retrieving card details: {e}")
    
    # Get plan information for invoices table
    invoices = []
    for record in billing_records:
        try:
            details_json = json.dumps(record.details)
            # Calculate billing period based on subscription start and end dates
            billing_period = f"{record.subscription.start_date.strftime('%B %d')} - {record.subscription.next_billing_date.strftime('%B %d')}"
            invoices.append({
                'id': record.id,
                'date': record.billing_date,
                'amount': record.amount,
                'plan': record.subscription.plan.name,
                'status': record.status,
                'billing_period': billing_period,
                'square_payment_id': record.square_payment_id,
                'square_invoice_id': record.square_invoice_id,
                'details': record.details,  # Original Python dict for template access
                'details_json': details_json  # JSON string for script tag
            })
        except Exception as e:
            print(f"Error processing billing record {record.id}: {e}")
            # Add a minimal record in case of error
            invoices.append({
                'id': record.id,
                'date': record.billing_date,
                'amount': record.amount,
                'plan': 'Unknown',
                'status': record.status,
                'square_payment_id': record.square_payment_id,
                'details': {}
            })
    
    context = {
        'billing_records': billing_records,  # Keep for backward compatibility
        'total_billed': total_billed,
        'current_balance': current_balance,  # Use the calculated current balance
        'last_payment': {
            'amount': last_payment.amount if last_payment else 0,
            'date': last_payment.billing_date if last_payment else None
        },
        'next_billing': next_billing,
        'payment_method': payment_method,
        'invoices': invoices,
        'active_page': 'billing_history',
        'title': 'Billing History'
    }
    
    return render(request, 'usage_analytics/billing_history.html', context)

@login_required
@require_POST
def change_plan(request):
    """Handle plan changes to take effect at the next billing date."""
    # Only accept POST requests
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)
    
    # Get plan IDs from JSON data
    try:
        # Parse JSON data from request body
        data = json.loads(request.body)
        new_plan_id = data.get('new_plan_id')
        current_plan_id = data.get('current_plan_id')

        if not new_plan_id or not current_plan_id:
            return JsonResponse({'status': 'error', 'message': 'Missing plan IDs'}, status=400)
        
        new_plan_id = int(new_plan_id)
        current_plan_id = int(current_plan_id)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid plan IDs'}, status=400)
    
    business = request.user.business_set.first()
    new_plan = get_object_or_404(SubscriptionPlan, pk=new_plan_id, is_active=True)
    
    # Check if business already has an active subscription
    try:
        current_subscription = business.active_subscription()
        
        # Don't change immediately, just mark for change at next billing date
        if current_subscription and current_subscription.plan.id == new_plan.id:
            return JsonResponse({
                'success': False, 
                'error': f"You are already subscribed to the {new_plan.name} plan."
            })
        else:
            # Store the new plan ID for changing at the next billing date
            current_subscription.next_plan_id = new_plan.id
            current_subscription.save()
            
            # Format the next billing date for display
            next_billing_date = current_subscription.next_billing_date.strftime('%B %d, %Y') if current_subscription.next_billing_date else "your next billing date"
            
            return JsonResponse({
                'success': True,
                'message': f"Your subscription will be changed from {current_subscription.plan.display_name} to {new_plan.display_name} on {next_billing_date}.",
                'plan_name': new_plan.name,
                'price': str(new_plan.price),
                'next_billing_date': next_billing_date
            })
        
    except BusinessSubscription.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "No active subscription found.",
            'redirect_url': reverse('subscription:select_plan', args=[new_plan_id])
        })

@login_required
@require_POST
def cancel_subscription(request):
    """Cancel a subscription."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests are allowed'}, status=405)
    
    business = request.user.business_set.first()
    
    try:
        # Get plan ID from JSON data
        data = json.loads(request.body)
        plan_id = data.get('plan_id')
        
        if not plan_id:
            return JsonResponse({'success': False, 'error': 'Missing plan ID'}, status=400)
        
        try:
            plan_id = int(plan_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid plan ID'}, status=400)
        
        # Find the subscription with the specified plan ID
        subscription = BusinessSubscription.objects.get(
            business=business,
            is_active=True,
            plan_id=plan_id
        )
        
        # Mark subscription as cancelled but keep it active until the next billing date
        subscription.status = 'cancelled'
        subscription.save()
        
        return JsonResponse({
            'success': True,
            'message': f"Your subscription to {subscription.plan.display_name} has been cancelled. You can continue using it until your next billing date on {subscription.next_billing_date.strftime('%B %d, %Y') if subscription.next_billing_date else 'the end of your current billing period'}."
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except BusinessSubscription.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "No active subscription found with the specified plan."
        })

@login_required
def get_subscription_data(request):
    """API endpoint to retrieve subscription data."""
    business = request.user.business_set.first()
    
    # Parse date range from request
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = timezone.now().date().replace(day=1)
            
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Get current subscription
    try:
        subscription = BusinessSubscription.objects.filter(
            business=business,
            is_active=True
        ).latest('created_at')
        
        plan_data = {
            'id': subscription.plan.id,
            'name': subscription.plan.display_name,
            'price': float(subscription.plan.price),
            'billing_cycle': subscription.plan.billing_cycle,
            'voice_minutes': subscription.plan.voice_minutes,
            'sms_messages': subscription.plan.sms_messages,
            'cleaners': subscription.plan.cleaners,
            'features': subscription.plan.features,
            'status': subscription.status,
            'start_date': subscription.start_date.strftime('%Y-%m-%d'),
            'end_date': subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else None,
            'days_remaining': subscription.days_remaining()
        }
    except BusinessSubscription.DoesNotExist:
        plan_data = None
    
    # Get usage metrics
    usage_summary = UsageTracker.get_usage_summary(
        business=business,
        start_date=start_date,
        end_date=end_date
    )
    
    # Get available plans (exclude invite-only plans)
    available_plans = []
    for plan in SubscriptionPlan.objects.filter(is_active=True, is_invite_only=False).order_by('price'):
        available_plans.append({
            'id': plan.id,
            'name': plan.display_name,
            'price': float(plan.price),
            'billing_cycle': plan.billing_cycle,
            'voice_minutes': plan.voice_minutes,
            'sms_messages': plan.sms_messages,
            'cleaners': plan.cleaners,
            'features': plan.features
        })
    
    response_data = {
        'current_plan': plan_data,
        'usage_metrics': usage_summary,
        'available_plans': available_plans
    }
    
    return JsonResponse(response_data)


@login_required
def select_plan(request, plan_id=None):
    """View for selecting a plan and proceeding to payment."""
    business = request.user.business_set.first()
    
   
    from saas.models import PlatformSettings
    platform_settings = PlatformSettings.objects.first()
    
    has_paid_setup_fee = business.has_setup_fee()

    if plan_id:
        # Get the specific plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            
           
            if plan.plan_tier == "trial" and not plan.is_invite_only:
                trial_already_availed = BusinessSubscription.objects.filter(business=business, plan__plan_tier="trial").exists()
                if trial_already_availed:
                    messages.error(request, "You have already availed the trial plan.")
                    return redirect('subscription:subscription_management')

        except SubscriptionPlan.DoesNotExist:
            messages.error(request, "The selected plan is not available.")
            return redirect('subscription:subscription_management')
    else:
        # Redirect to subscription management if no plan_id
        return redirect('subscription:subscription_management')
    
    # Get current subscription
   
    subscription = business.active_subscription()
    
    # If user already has this plan, redirect to subscription management
    if subscription:
        messages.info(request, f"You already have an active subscription. with status {subscription.status} ending on {subscription.end_date}")
        return redirect('subscription:subscription_management')
            
  
    
    # Get card details from Square if available
    card_details = None
    if business.square_card_id and business.square_customer_id:
        try:
            # Initialize Square client
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Retrieve the card details
            card_result = square_client.cards.retrieve_card(
                card_id=business.square_card_id
            )
            
            if card_result.is_success():
                card = card_result.body.get('card', {})
                card_details = {
                    'last4': card.get('last_4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                    'card_brand': card.get('card_brand')
                }
        except Exception as e:
            # Log the error but don't crash
            print(f"Error retrieving card details: {e}")
    
    # Prepare context for the template
    context = {
        'plan': plan,
        'subscription': subscription,
        'business': business,
        'card_details': card_details,
        'square_app_id': settings.SQUARE_APP_ID,
        'environment': settings.SQUARE_ENVIRONMENT,
        'active_page': 'subscription',
        'title': 'Select Plan',
        'platform_settings': platform_settings,
        'has_paid_setup_fee': has_paid_setup_fee
    }
    
    return render(request, 'subscription/payment.html', context)

@login_required
@require_POST
def process_payment(request, plan_id):
    """Process the payment for a subscription plan."""
    try:
        # Get the plan
        plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
        business = request.user.business_set.first()
        
        # Check if setup fee should be applied (only on first purchase)
        platform_settings = PlatformSettings.objects.first()
        setup_fee_amount = platform_settings.setup_fee_amount
        apply_setup_fee = True
        try:
            has_setup_fee = business.has_setup_fee()
            if has_setup_fee:
                apply_setup_fee = False
        except Exception as e:
            print(f"Error checking setup fee: {str(e)}")
        
        # Get payment details from form
        card_nonce = request.POST.get('card-nonce')
        use_existing_card = request.POST.get('use_existing_card') == 'true'
        is_free_subscription = request.POST.get('is_free_subscription') == 'true'
        
        # Get coupon code if applied
        coupon_code = request.POST.get('coupon_code')
        coupon = None
        
        
        final_price = plan.get_display_price()
        
        # Add setup fee to final price if applicable
        original_plan_price = final_price
        if apply_setup_fee:
            final_price += float(setup_fee_amount)
        
    
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code.upper(), is_active=True)
                
                # Validate coupon
                if coupon.is_valid() and coupon.is_valid_for_user(request.user):
                    # Check if coupon is applicable to this plan
                    if coupon.applicable_plans.filter(id=plan.id).exists() or not coupon.applicable_plans.exists():
                        final_price = coupon.apply_discount(final_price)
                    else:
                        coupon = None
                else:
                    coupon = None
            except Coupon.DoesNotExist:
                pass
        
        print(f"Final Price: {final_price}")
        final_price = 0 #For Testing
        # Check if the final price is zero (free subscription)
        is_free = final_price <= 0 or is_free_subscription
        
        print(f"Coupon Code: {coupon_code}")
        print(f"Coupon: {coupon}")
        print(f"Final Price: {final_price}")

        # Generate a unique transaction ID for free subscriptions or process payment
        transaction_id = str(uuid.uuid4())  # Default transaction ID for free subscriptions
        card_details = {}
        card_last4 = '****'
        customer_id = business.square_customer_id if business.square_customer_id else None
        card_id = business.square_card_id if business.square_card_id else None
        
        # Only process payment if the final price is greater than zero
        if not is_free:
            # Initialize Square client
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Prepare payment amount
            amount_money = {
                "amount": int(final_price * 100),  # Convert to cents
                "currency": "USD"
            }
            
            # Generate a unique idempotency key for this payment
            idempotency_key = str(uuid.uuid4())
            
            # If using existing card, get the customer and card IDs
            if use_existing_card:
                customer_id = business.square_customer_id
                card_id = business.square_card_id
            
            # Create the payment
            payment_body = {
                "idempotency_key": idempotency_key,
                "amount_money": amount_money,
                "autocomplete": True,
                "note": f"Subscription to {plan.name} ({plan.billing_cycle})",
                "payment_method_types": ["CARD"]
            }
            
            # Add source ID (card nonce) or source (saved card)
            if use_existing_card and business.square_card_id:
                payment_body["source_id"] = business.square_card_id
                payment_body["customer_id"] = business.square_customer_id
            else:
                # If no card nonce and not using existing card, redirect back
                if not card_nonce and not use_existing_card:
                    return redirect('subscription:select_plan', plan_id=plan_id)
                payment_body["source_id"] = card_nonce
            
            # Process the payment
            payment_result = square_client.payments.create_payment(
                body=payment_body
            )
            
            if not payment_result.is_success():
                messages.error(request, "Failed to process payment. Please try again")
                return redirect('subscription:select_plan', plan_id=plan_id)
                
            if payment_result.is_success():
                payment = payment_result.body['payment']
                transaction_id = payment['id']
                card_details = payment.get('card_details', {})
                card_last4 = card_details.get('card', {}).get('last_4', '****')
        
        # Check if the business already has an active subscription
        with transaction.atomic():
            try:
                current_subscription = business.active_subscription()
                if current_subscription:
                    # End the current subscription
                    current_subscription.is_active = False
                    current_subscription.end_date = timezone.now()
                    current_subscription.save()
                
            except BusinessSubscription.DoesNotExist:
                print("No active subscription found for this business.")
            
            # Create new subscription
            end_date = plan.get_next_billing_date()
            
            new_subscription = BusinessSubscription.objects.create(
                business=business,
                plan=plan,
                status='active',
                start_date=timezone.now(),
                end_date=end_date,
                next_billing_date=end_date,
                square_subscription_id=transaction_id,  # Using Square payment ID
                square_customer_id=customer_id if customer_id else None,
                coupon_used=coupon  # Store the coupon used for this subscription
            )
            
            # Create a billing record for this transaction
            billing_record = BillingHistory.objects.create(
                business=business,
                subscription=new_subscription,
                amount=final_price,  # Use discounted price if coupon applied
                status='paid',
                billing_date=timezone.now(),
                square_payment_id=transaction_id,  # Store the transaction ID (Square payment ID or UUID for free)
                square_invoice_id=transaction_id,  # For now, using the same ID for both
                details={
                    'payment_method': 'square' if not is_free else 'free',
                    'payment_date': timezone.now().isoformat(),
                    'customer_id': customer_id if customer_id else None,
                    'card_id': card_id if card_id else None,
                    'payment_status': 'COMPLETED',
                    'coupon_code': coupon_code if coupon_code else "No Coupon",
                    'discount_amount': float(original_plan_price - final_price + float(setup_fee_amount)) if coupon_code else 0.00,
                    'is_free': is_free,
                    'setup_fee_applied': apply_setup_fee,
                    'setup_fee_amount': float(setup_fee_amount)
                }
            )

            print({
                    'coupon_code': coupon_code if coupon_code else "No Coupon",
                    'discount_amount': float(original_plan_price - final_price) if coupon_code else 0.00,
                    'is_free': is_free,
                    'setup_fee_applied': apply_setup_fee,
                    'setup_fee_amount': float(setup_fee_amount)
                })
            
            from .models import SetupFee
            if apply_setup_fee:
                setup_fee_obj = SetupFee.objects.create(
                    business=business,
                    amount=setup_fee_amount)

            # Coupon usage is automatically recorded in the BusinessSubscription.save() method
            # No need to record it here to avoid double-counting

            if not business.isApproved or not business.isActive:
                business.isApproved = True
                business.isActive = True
                business.save()
            
            # Create usage tracker for the new subscription's business
            UsageTracker.objects.get_or_create(
                business=new_subscription.business,
                date=timezone.now().date(),
                defaults={'metrics': {}}  # Initialize with empty metrics
            )
        
        if plan.plan_type == 'trial':
            # Redirect to trial success page for trial plans
            return redirect('subscription:trial_success', subscription_id=new_subscription.id)
        
        # Return success page
        return redirect('subscription:subscription_success', subscription_id=new_subscription.id, transaction_id=transaction_id)
    
    except Exception as e:
        print(f"Error processing payment: {str(e)}")
        return redirect('subscription:select_plan', plan_id=plan_id)

@login_required
def subscription_success(request, subscription_id, transaction_id):
    """Show subscription success page after successful payment."""
    business = request.user.business_set.first()
    subscription = get_object_or_404(BusinessSubscription, id=subscription_id, business=business)

    is_first_purchase = BusinessSubscription.objects.filter(business=business).exists() == 1
    
    # Get billing history record for this transaction to show payment details
    billing_record = BillingHistory.objects.filter(
        subscription_id=subscription_id,
        square_payment_id=transaction_id
    ).first()
    
    # Initialize payment details
    payment_details = {
        'original_price': subscription.plan.get_display_price(),
        'discount_amount': 0,
        'final_amount': subscription.plan.get_display_price(),
        'coupon_code': None,
        'coupon_applied': False,
        'setup_fee_applied': False,
        'setup_fee_amount': 0
    }
    
    # If we have billing record with details, use that information
    if billing_record:
        payment_details['final_amount'] = billing_record.amount
        
        # Check if coupon was applied
        if billing_record.details and 'coupon_code' in billing_record.details:
            payment_details['coupon_code'] = billing_record.details.get('coupon_code')
            payment_details['discount_amount'] = billing_record.details.get('discount_amount', 0)
            payment_details['original_price'] = billing_record.amount
            payment_details['coupon_applied'] = True
        
        # Check if setup fee was applied
        if billing_record.details and 'setup_fee_applied' in billing_record.details:
            payment_details['setup_fee_applied'] = billing_record.details.get('setup_fee_applied', False)
            payment_details['setup_fee_amount'] = billing_record.details.get('setup_fee_amount', 0)
    
    # Count active business subscriptions
    business_subscriptions_count = BusinessSubscription.objects.filter(
        business=business,
        is_active=True
    ).count()
    
    context = {
        'subscription': subscription,
        'transaction_id': transaction_id,
        'payment_details': payment_details,
        'active_page': 'subscription',
        'title': 'Subscription Successful',
        'business_subscriptions_count': business_subscriptions_count
    }
    
    return render(request, 'subscription/success.html', context)

@login_required
def trial_success(request, subscription_id):
    """Show trial success page after successful trial activation."""
    business = request.user.business_set.first()
    subscription = get_object_or_404(BusinessSubscription, id=subscription_id, business=business)
    
    # Calculate trial end date
    trial_end_date = subscription.plan.get_next_billing_date()
    
    context = {
        'subscription': subscription,
        'trial_end_date': trial_end_date,
        'active_page': 'subscription',
        'title': 'Trial Activated Successfully'
    }
    
    return render(request, 'accounts/trial_success.html', context)

@login_required
def cancel_plan_change(request):
    """Cancel a scheduled plan change."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests are allowed'}, status=405)
    
    business = request.user.business_set.first()
    
    try:
        subscription = BusinessSubscription.objects.get(business=business, is_active=True)
        
        if not subscription.next_plan_id:
            return JsonResponse({'success': False, 'error': 'No plan change scheduled'})
        
        # Get the plan name before clearing it for the message
        try:
            next_plan = SubscriptionPlan.objects.get(id=subscription.next_plan_id)
            plan_name = next_plan.name
        except SubscriptionPlan.DoesNotExist:
            plan_name = "new plan"
        
        # Clear the next plan ID
        subscription.next_plan_id = None
        subscription.save()
        
        return JsonResponse({
            'success': True,
            'message': f"Your scheduled change to {plan_name} has been canceled."
        })
        
    except BusinessSubscription.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No active subscription found'})

@login_required
def validate_coupon(request):
    """API endpoint to validate a coupon code."""
    if request.method != 'POST':
        return JsonResponse({'valid': False, 'message': 'Invalid request method'})
    
    data = json.loads(request.body)
    code = data.get('coupon_code')
    plan_id = data.get('plan_id')

    print(code, plan_id)


    
    if not code or not plan_id:
        return JsonResponse({'valid': False, 'message': 'Missing required parameters'})
    
    try:
        # Get the coupon and plan
        coupon = Coupon.objects.get(code=code.upper(), is_active=True)
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        
        # Check if the coupon is valid for this user and plan
        user = request.user
        
        # Check if the coupon is valid
        if not coupon.is_valid():
            return JsonResponse({'valid': False, 'message': 'This coupon is no longer valid'})
        
        # Check if the coupon is valid for this user
        if not coupon.is_valid_for_user(user):
            return JsonResponse({'valid': False, 'message': 'You have already used this coupon the maximum number of times'})
        
        # Check if the coupon is applicable to this plan
        if coupon.applicable_plans.exists() and not coupon.applicable_plans.filter(id=plan.id).exists():
            return JsonResponse({'valid': False, 'message': 'This coupon is not valid for the selected plan'})
        
        # Calculate the discount
        original_price = float(plan.price)
        discount_amount = float(coupon.calculate_discount(original_price))
        discounted_price = float(coupon.apply_discount(original_price))

        print(original_price, discount_amount, discounted_price)
        
        # Format the discount description
        if coupon.discount_type == 'percentage':
            discount_description = f"{coupon.discount_value}% off"
        else:
            discount_description = f"${coupon.discount_value} off"
        
        print({
            'valid': True,
            'message': 'Coupon applied successfully!',
            'discount_amount': round(discount_amount, 2),
            'discounted_price': round(discounted_price, 2),
            'discount_description': discount_description,
            'coupon_code': coupon.code
        })

        return JsonResponse({
            'valid': True,
            'message': 'Coupon applied successfully!',
            'discount_amount': round(discount_amount, 2),
            'discount_type': coupon.discount_type,
            'discount_value': coupon.discount_value,
            'discounted_price': round(discounted_price, 2),
            'discount_description': discount_description,
            'coupon_code': coupon.code,
        })
    
    except Coupon.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid coupon code'})
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid subscription plan'})
    except Exception as e:
        return JsonResponse({'valid': False, 'message': f'An error occurred: {str(e)}'})

@login_required
def manage_card(request):
    """View for saving or updating card details."""
    business = request.user.business_set.first()

    
    # Get redirect URL if provided
    redirect_url = request.GET.get('redirect_url') or request.POST.get('redirect_url')
    
    # Get card details from Square if available
    card_details = None
    if business.square_card_id and business.square_customer_id:
        try:
            # Initialize Square client
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Retrieve the card details
            card_result = square_client.cards.retrieve_card(
                card_id=business.square_card_id
            )
            
            if card_result.is_success():
                card = card_result.body.get('card', {})
                card_details = {
                    'last4': card.get('last_4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                    'card_brand': card.get('card_brand')
                }
        except Exception as e:
            # Log the error but don't crash
            print(f"Error retrieving card details: {e}")
    
    if request.method == 'POST':
        # Get the card nonce from the request
        card_nonce = request.POST.get('card-nonce')
        
        if not card_nonce:
            messages.error(request, "No card information received. Please try again.")
            context = {
                'business': business,
                'card_details': card_details,
                'square_app_id': settings.SQUARE_APP_ID,
                'environment': settings.SQUARE_ENVIRONMENT,
                'redirect_url': redirect_url,
                'active_page': 'subscription',
                'title': 'Manage Payment Method'
            }
            return render(request, 'subscription/manage_card.html', context)
        
        if card_nonce and not card_nonce.startswith('cnon:'):
            messages.error(request, "Invalid card token received. Please try again.")
            context = {
                'business': business, 
                'card_details': card_details,
                'square_app_id': settings.SQUARE_APP_ID,
                'environment': settings.SQUARE_ENVIRONMENT,
                'redirect_url': redirect_url,
                'active_page': 'subscription',
                'title': 'Manage Payment Method'
            }
            return render(request, 'subscription/manage_card.html', context)
        
        # Initialize Square client
        square_client = Client(
            access_token=settings.SQUARE_ACCESS_TOKEN,
            environment=settings.SQUARE_ENVIRONMENT
        )
        
        # Check if business already has a Square customer ID
        if not business.square_customer_id:
            # Create a new customer
            customer_request = {
                'given_name': request.user.first_name or business.businessName,
                'family_name': request.user.last_name or "",
                'email_address': request.user.email,
                'reference_id': str(business.businessId),
                'phone_number': business.phone
            }
            
            customer_result = square_client.customers.create_customer(
                body=customer_request
            )

            print(customer_result)
            
            if customer_result.is_success():
                customer_id = customer_result.body['customer']['id']
                business.square_customer_id = customer_id  # Store Square customer ID
                business.save()
            else:
                messages.error(request, "Failed to create payment profile. Please try again.")
                context = {
                    'business': business,
                    'card_details': card_details,
                    'square_app_id': settings.SQUARE_APP_ID,
                    'environment': settings.SQUARE_ENVIRONMENT,
                    'redirect_url': redirect_url,
                    'active_page': 'subscription',
                    'title': 'Manage Payment Method'
                }
                return render(request, 'subscription/manage_card.html', context)
        else:
            customer_id = business.square_customer_id
        
        # Create a card for the customer
        idempotency_key = str(uuid.uuid4())
        
        card_request = {
            'idempotency_key': idempotency_key,
            'source_id': card_nonce,
            'card': {
                'customer_id': customer_id,
                'cardholder_name': f"{request.user.first_name} {request.user.last_name}".strip() or business.businessName,
            }
        }
        
        try:
            card_result = square_client.cards.create_card(
                body=card_request
            )
            
            if card_result.is_success():
                card_id = card_result.body['card']['id']
                # Store the card ID in the business model
                business.square_card_id = card_id
                business.save()
                
                # Check if there was a redirect URL
                messages.success(request, "Payment method saved successfully.")
                if redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect('subscription:subscription_management')
            else:
                error_message = "Failed to save payment method."
                
                # Try to extract more specific error info
                if card_result.errors:
                    first_error = card_result.errors[0]
                    error_detail = first_error.get('detail', '')
                    error_code = first_error.get('code', '')
                    
                    if error_code in ['INVALID_CARD_DATA', 'INVALID_EXPIRATION_DATE', 'VERIFY_CVV_FAILURE', 'VERIFY_AVS_FAILURE']:
                        error_message = f"Invalid card information: {error_detail or 'Please check your card details and try again.'}"
                    elif error_code == 'CARD_DECLINED':
                        error_message = "Your card was declined. Please try another card."
                    elif error_code == 'CARD_PROCESSING_NOT_ENABLED':
                        error_message = "Card processing is not enabled on this account."
                
                messages.error(request, error_message)
        except Exception as e:
            messages.error(request, "An unexpected error occurred. Please try again.")
    
    # Render the form for GET requests or if there was an error
    context = {
        'business': business,
        'card_details': card_details,
        'square_app_id': settings.SQUARE_APP_ID,
        'environment': settings.SQUARE_ENVIRONMENT,
        'redirect_url': redirect_url,
        'active_page': 'subscription',
        'title': 'Manage Payment Method'
    }
    return render(request, 'subscription/manage_card.html', context)

@login_required
@require_POST
def update_auto_upgrade(request):
    """Update the auto-upgrade setting for a business."""
    try:
        # Parse the request data
        data = json.loads(request.body)
        auto_upgrade = data.get('auto_upgrade', False)
        print(f"auto_upgrade: {auto_upgrade}")
        
        # Get the business
        business = request.user.business_set.first()
        if not business:
            return JsonResponse({
                'success': False,
                'message': 'No business found for this user.'
            })
        
        # Update the auto-upgrade setting
        business.auto_upgrade = auto_upgrade
        print(f"business.auto_upgrade: {business.auto_upgrade}")
        business.save()
        
        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Auto-upgrade setting updated successfully.'
        })
    
    except Exception as e:
        # Log the error
        print(f"Error updating auto-upgrade setting: {e}")
        
        # Return error response
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })

def delete_card(request):
    if request.method == 'POST':
        try:
            # Get the business instance
            business = request.user.business_set.first()
            
            if not business.square_card_id:
                messages.error(request, 'No card found to delete.')
                return redirect('subscription:manage_card')
            
            # Initialize Square client
            square_client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment=settings.SQUARE_ENVIRONMENT
            )
            
            # Delete the card from Square
            try:
                
                result = square_client.customers.delete_customer_card(
                    customer_id=business.square_customer_id,
                    card_id=business.square_card_id
                )
                if result.is_success():
                    # Clear the card ID from the business model
                    business.square_card_id = None
                    business.save()
                    messages.success(request, 'Card successfully deleted.')
                else:
                    messages.error(request, 'Failed to delete card from Square.')
            except Exception as e:
                messages.error(request, f'Error deleting card from Square: {str(e)}')
                return redirect('subscription:manage_card')
            
        except Exception as e:
            messages.error(request, f'Error deleting card: {str(e)}')
    
    # Redirect back to the card management page
    return redirect('subscription:manage_card')

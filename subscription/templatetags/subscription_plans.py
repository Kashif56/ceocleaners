from django import template
from subscription.models import SubscriptionPlan

register = template.Library()

@register.simple_tag
def get_subscription_plans():
    """Return all active subscription plans"""
    return SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order')

@register.filter
def filter_plans(plans, name_contains):
    """Filter plans by name (legacy support)"""
    return [plan for plan in plans if name_contains in plan.name]

@register.filter
def filter_plans_by_tier(plans, tier):
    """Filter plans by tier"""
    return [plan for plan in plans if plan.plan_tier == tier]

@register.filter
def filter_plans_by_billing_cycle(plans, billing_cycle):
    """Filter plans by billing cycle"""
    return [plan for plan in plans if plan.billing_cycle == billing_cycle]
from django import template
from subscription.models import SetupFee

register = template.Library()

@register.simple_tag(takes_context=True)
def get_setup_fee_status(context):
    """
    Get the setup fee status for the current user's business.
    Returns the SetupFee object if it exists, otherwise None.
    """
    request = context['request']
    if request.user.is_authenticated and hasattr(request.user, 'business_set'):
        business = request.user.business_set.first()
        if business:
            return SetupFee.objects.filter(business=business).first()
    return None

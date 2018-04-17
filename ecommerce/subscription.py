import logging
import stripe

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from ecommerce.core.models import User
from django.conf import settings

logger = logging.getLogger(__name__)

import urllib 
@ensure_csrf_cookie
def unsubscribe(request):
    """
    unsubscribe from a course  

    """
    NAME = 'stripe'
    partner_short_code = 'EDX'
    configuration = settings.PAYMENT_PROCESSOR_CONFIG[partner_short_code.lower()][NAME.lower()]
    publishable_key = configuration['publishable_key']
    secret_key = configuration['secret_key']
    country = configuration['country']
    stripe.api_key = secret_key
    username = request.GET.get('username', None)
    course_id = request.GET.get('course_id', None)
    print "course id", urllib.quote_plus(course_id)
    user = User.objects.get(username=username)

    try:
        print user.meta_data
        customer = stripe.Customer.retrieve(user.meta_data['stripe'][course_id]['customer_id'])
        subscription = stripe.Subscription.retrieve(user.meta_data['stripe'][course_id]['subscription_id'])
        subscription.delete(at_period_end = True)
        return JsonResponse({'Sunscription cancelled for user': username}, status=200)
    except Exception, e:
        logger.error(e)
       
        return JsonResponse({"error": str(e)}, status=400)
       
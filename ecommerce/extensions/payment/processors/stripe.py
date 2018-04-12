""" Stripe payment processing. """
from __future__ import absolute_import, unicode_literals

import logging

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from ecommerce.core.models import User
from django.conf import settings

import stripe
from oscar.apps.payment.exceptions import GatewayError, TransactionDeclined
from oscar.core.loading import get_model


from django.http import JsonResponse

from ecommerce.extensions.payment.constants import STRIPE_CARD_TYPE_MAP
from ecommerce.extensions.payment.processors import (
    ApplePayMixin,
    BaseClientSidePaymentProcessor,
    HandledProcessorResponse
)

logger = logging.getLogger(__name__)

BillingAddress = get_model('order', 'BillingAddress')
Country = get_model('address', 'Country')
PaymentEvent = get_model('order', 'PaymentEvent')
PaymentEventType = get_model('order', 'PaymentEventType')
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')
Source = get_model('payment', 'Source')
SourceType = get_model('payment', 'SourceType')


class Stripe(ApplePayMixin, BaseClientSidePaymentProcessor):
    NAME = 'stripe'
    template_name = 'payment/stripe.html'

    def __init__(self, site):
        """
        Constructs a new instance of the Stripe processor.

        Raises:
            KeyError: If no settings configured for this payment processor.
        """
        super(Stripe, self).__init__(site)
        configuration = self.configuration
        self.publishable_key = configuration['publishable_key']
        self.secret_key = configuration['secret_key']
        self.country = configuration['country']

        stripe.api_key = self.secret_key

    def get_transaction_parameters(self, basket, request=None, use_client_side_checkout=True, **kwargs):
        raise NotImplementedError('The Stripe payment processor does not support transaction parameters.')

    def _get_basket_amount(self, basket):
        return str((basket.total_incl_tax * 100).to_integral_value())

    def handle_processor_response(self, response, basket=None):
        token = response
        order_number = basket.order_number
        currency = basket.currency

        """
            TODO:
            ADD: a get_production method to the basker model
            ADD: is_subscription check to this processot responce "basket.get_product().course.is_subscription"
            ADD: split this payment processor to handle the creation of the subscription in stripe https://stripe.com/docs/api#create_subscription
            ORDER OF EVENTS: create a customer https://stripe.com/docs/api#create_customer
                Create the subscription with the use of the customer, and then fire a charge to the subscription.
        """

        # NOTE: In the future we may want to get/create a Customer. See https://stripe.com/docs/api#customers.

        user = basket.owner
        if basket.all_lines()[0].product.course.is_subscription is True:
            try:
                plan_name = basket.all_lines()[0].product.course.subscription_plan_name
                customer = stripe.Customer.create(
                    source= token,
                ) 
                subscription = stripe.Subscription.create(
                   customer=customer.id,
                   items=[{'plan': plan_name}],
                )
                user.meta_data = { 
                    "stripe": {
                        "customer_id": customer.id,
                        "subscription_id": subscription.id
                    }
                }
                user.save()
                print type(subscription)
                transaction_id=subscription.id
                subscription_json = json.dumps(subscription, sort_keys=True, indent=2)
                subscription_dict = json.loads(subscription_json)
                card_number = '' #subscription.source.last4
                card_type = '' #STRIPE_CARD_TYPE_MAP.get(subscription.source.brand)

                self.record_processor_response(subscription_json, transaction_id=str(subscription.id), basket=basket)
            except stripe.error.CardError as ex:
                msg = 'Stripe subscription for basket [%d] declined with HTTP status [%d]'
                body = ex.json_body
                logger.exception(msg + ': %s', basket.id, ex.http_status, body)
                self.record_processor_response(body, basket=basket)
                raise TransactionDeclined(msg, basket.id, ex.http_status)
        
        elif basket.all_lines()[0].product.course.is_subscription is False:
            try:      
                charge = stripe.Charge.create(
                    amount=self._get_basket_amount(basket),
                    currency=currency,
                    source=token,
                    description=order_number,
                    metadata={'order_number': order_number}
                )
                transaction_id = charge.id
                card_number = charge.source.last4
                card_type = STRIPE_CARD_TYPE_MAP.get(charge.source.brand)

                # NOTE: Charge objects subclass the dict class so there is no need to do any data transformation
                # before storing the response in the database.
                self.record_processor_response(charge, transaction_id=transaction_id, basket=basket)
                logger.info('Successfully created Stripe charge [%s] for basket [%d].', transaction_id, basket.id)
            except stripe.error.CardError as ex:
                msg = 'Stripe payment for basket [%d] declined with HTTP status [%d]'
                body = ex.json_body
                logger.exception(msg + ': %s', basket.id, ex.http_status, body)
                self.record_processor_response(body, basket=basket)
                raise TransactionDeclined(msg, basket.id, ex.http_status)

        total = basket.total_incl_tax
        
        return HandledProcessorResponse(
            transaction_id=transaction_id,
            total=total,
            currency=currency,
            card_number=card_number,
            card_type=card_type
        )

        #return JsonResponse({'status': 'status'}, status=200)
 

    def issue_credit(self, order_number, basket, reference_number, amount, currency):
        try:
            refund = stripe.Refund.create(charge=reference_number)
        except:
            msg = 'An error occurred while attempting to issue a credit (via Stripe) for order [{}].'.format(
                order_number)
            logger.exception(msg)
            raise GatewayError(msg)

        transaction_id = refund.id

        # NOTE: Refund objects subclass dict so there is no need to do any data transformation
        # before storing the response in the database.
        self.record_processor_response(refund, transaction_id=transaction_id, basket=basket)

        return transaction_id

    def get_address_from_token(self, token):
        """ Retrieves the billing address associated with token.

        Returns:
            BillingAddress
        """
        data = stripe.Token.retrieve(token)['card']
        address = BillingAddress(
            first_name=data['name'],    # Stripe only has a single name field
            last_name='',
            line1=data['address_line1'],
            line2=data.get('address_line2') or '',
            line4=data['address_city'],  # Oscar uses line4 for city
            postcode=data.get('address_zip') or '',
            state=data.get('address_state') or '',
            country=Country.objects.get(iso_3166_1_a2__iexact=data['address_country'])
        )
        return address

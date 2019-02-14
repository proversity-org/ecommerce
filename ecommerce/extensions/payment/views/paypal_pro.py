""" Views for interacting with the payment processor. """
from __future__ import unicode_literals

import logging

from django.core.exceptions import MultipleObjectsReturned
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, QueryDict
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import View
from oscar.apps.partner import strategy
from oscar.apps.payment.exceptions import PaymentError
from oscar.core.loading import get_class, get_model

from ecommerce.extensions.checkout.mixins import EdxOrderPlacementMixin
from ecommerce.extensions.checkout.utils import get_receipt_page_url
from ecommerce.extensions.payment.processors.paypal_pro import PaypalPro

logger = logging.getLogger(__name__)

Applicator = get_class('offer.utils', 'Applicator')
Basket = get_model('basket', 'Basket')
BillingAddress = get_model('order', 'BillingAddress')
Country = get_model('address', 'Country')
NoShippingRequired = get_class('shipping.methods', 'NoShippingRequired')
OrderNumberGenerator = get_class('order.utils', 'OrderNumberGenerator')
OrderTotalCalculator = get_class('checkout.calculators', 'OrderTotalCalculator')
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')


class PaypalProPaymentExecutionView(EdxOrderPlacementMixin, View):
    """Execute an approved PayPal payment and place an order for paid products as appropriate."""

    @property
    def payment_processor(self):
        return PaypalPro(self.request.site)

    @csrf_exempt
    @method_decorator(transaction.non_atomic_requests)
    def dispatch(self, request, *args, **kwargs):
        return super(PaypalProPaymentExecutionView, self).dispatch(request, *args, **kwargs)

    def _get_basket(self, transaction_id):
        """
        Retrieve a basket using a transaction ID.

        Arguments:
            transaction_id: transaction_id create to identify the basket.

        Returns:
            It will return related basket

        """
        try:
            basket = PaymentProcessorResponse.objects.get(
                processor_name=self.payment_processor.NAME,
                transaction_id=transaction_id
            ).basket
            basket.strategy = strategy.Default()
            Applicator().apply(basket, basket.owner, self.request)
            return basket
        except MultipleObjectsReturned:
            logger.warning(u"Duplicate payment ID [%s] received from PayPal.", transaction_id)
            return None
        except Exception:
            logger.exception(u"Unexpected error during basket retrieval while executing PayPal payment.")
            return None

    def _get_processor_response(self, transaction_id):
        """
        """
        try:
            return PaymentProcessorResponse.objects.get(
                processor_name=self.payment_processor.NAME,
                transaction_id=transaction_id
            )
        except MultipleObjectsReturned:
            logger.warning(u"Duplicate payment ID [%s] received from PayPal.", transaction_id)
            return None

    def get(self, request, transaction_id):
        """Handle an incoming user returned to us by PayPal after approving payment."""
        processor_response = self._get_processor_response(transaction_id)

        if not processor_response:
            return redirect(self.payment_processor.error_url)

        paypal_response = processor_response.response

        status = paypal_response.get('payment_status', 'Undefined')

        if status != 'Completed':
            request.POST = QueryDict('', mutable=True)
            request.POST.update(paypal_response)
            response = self.post(request, transaction_id)

            if response.status_code != 201:
                return HttpResponse(
                    'Payment status is {} reason {}'.format(status, paypal_response.get('pending_reason', 'Undefined'))
                )

        basket = processor_response.basket
        basket.strategy = strategy.Default()
        Applicator().apply(basket, basket.owner, self.request)

        receipt_url = get_receipt_page_url(
            order_number=basket.order_number,
            site_configuration=basket.site.siteconfiguration
        )

        return redirect(receipt_url)

    def post(self, request, transaction_id):
        """
        This method store the result for the transaction
        """
        basket = self._get_basket(transaction_id)

        if not basket:
            raise Http404

        paypal_response = request.POST.dict()
        paypal_response['transaction_id'] = transaction_id

        try:
            with transaction.atomic():
                try:
                    self.handle_payment(paypal_response, basket)
                except PaymentError:
                    return HttpResponseBadRequest()
        except Exception:
            logger.exception('Attempts to handle payment for basket [%d] failed.', basket.id)
            return HttpResponseBadRequest()

        try:
            shipping_method = NoShippingRequired()
            shipping_charge = shipping_method.calculate(basket)
            order_total = OrderTotalCalculator().calculate(basket, shipping_charge)

            user = basket.owner
            # Given a basket, order number generation is idempotent. Although we've already
            # generated this order number once before, it's faster to generate it again
            # than to retrieve an invoice number from PayPal.
            order_number = basket.order_number

            self.handle_order_placement(
                order_number=order_number,
                user=user,
                basket=basket,
                shipping_address=None,
                shipping_method=shipping_method,
                shipping_charge=shipping_charge,
                billing_address=None,
                order_total=order_total,
                request=request
            )

            return HttpResponse(status=201)
        except Exception:
            logger.exception(self.order_placement_failure_msg, basket.id)
            return HttpResponseBadRequest()

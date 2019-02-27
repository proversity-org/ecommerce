""" Views for interacting with the payment processor. """
from __future__ import unicode_literals

import logging
import requests

from django.core.exceptions import MultipleObjectsReturned
from django.db import transaction
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect, render
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

        def get_transaction_state(status, reason):
            if not status:
                message = 'Waiting for Paypal response... Reload the page to update the state'
                return render(request, 'checkout/payment_pending.html', {'message': message})
            else:
                return render(request, 'checkout/payment_pending.html', {'payment_processor_name': 'Paypal'})

        processor_response = self._get_processor_response(transaction_id)
        basket = self._get_basket(transaction_id)

        if not processor_response or not basket:
            return redirect(self.payment_processor.error_url)

        paypal_response = processor_response.response
        status = paypal_response.get('payment_status')
        tx = request.GET.get('tx')

        if tx and status != 'Completed':
            paypal_response['txn_id'] = tx
            paypal_response['transaction_id'] = transaction_id

            try:
                self._validate_payment(basket, request, paypal_response)
            except PaypalProException:
                return get_transaction_state(status, paypal_response.get('pending_reason'))
        elif status != 'Completed':
            return get_transaction_state(status, paypal_response.get('pending_reason'))

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
        paypal_response = request.POST.dict()

        if not basket or not self._verify_paypal_origin(paypal_response):
            raise Http404

        paypal_response['transaction_id'] = transaction_id

        try:
            self.payment_processor.update_processor_response(transaction_id, paypal_response)
            self._validate_payment(basket, request, paypal_response)
        except PaypalProException:
            pass
        return redirect('paypal_pro:execute', transaction_id=transaction_id)

    def _validate_payment(self, basket, request, paypal_response):
        """
        This validate the payment using the paypal response
        """
        try:
            with transaction.atomic():
                try:
                    self.handle_payment(paypal_response, basket)
                except PaymentError:
                    raise PaypalProException
        except Exception:
            logger.exception('Attempts to handle payment for basket [%d] failed.', basket.id)
            raise PaypalProException

        try:
            shipping_method = NoShippingRequired()
            shipping_charge = shipping_method.calculate(basket)
            order_total = OrderTotalCalculator().calculate(basket, shipping_charge)

            user = basket.owner
            # Given a basket, order number generation is idempotent. Although we've already
            # generated this order number once before, it's faster to generate it again
            # than to retrieve an invoice number from PayPal.
            order_number = basket.order_number

            try:
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
            except ValueError:
                pass

        except Exception:
            logger.exception(self.order_placement_failure_msg, basket.id)
            raise PaypalProException

    def _verify_paypal_origin(self, data):
        """
        This verifies if the request is from paypal
        """
        if self.payment_processor.configuration.get('mode') == 'sandbox':
            url = 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr'
        else:
            url = 'https://ipnpb.paypal.com/cgi-bin/webscr'

        data['cmd'] = "_notify-validate"

        response = requests.post(url, data=data)

        return response.text == 'VERIFIED'


class PaypalProException(Exception):
    """Exception when the pay has not been validate successful"""
    pass

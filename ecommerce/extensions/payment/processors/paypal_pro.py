""" PayPal Pro payment processing. """
from __future__ import unicode_literals

import logging
import requests
import uuid
from urlparse import urljoin

from django.core.urlresolvers import reverse
from django.http import QueryDict
from oscar.core.loading import get_model
from oscar.apps.payment.exceptions import GatewayError, PaymentError

from ecommerce.core.url_utils import get_ecommerce_url
from ecommerce.extensions.payment.processors import BasePaymentProcessor, HandledProcessorResponse

logger = logging.getLogger(__name__)
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')


class PaypalPro(BasePaymentProcessor):
    """
    PayPal Pro
    """

    NAME = 'paypal_pro'
    DEFAULT_PROFILE_NAME = 'default'

    def __init__(self, site):
        """
        Constructs a new instance of the PayPal processor.

        Raises:
            KeyError: If a required setting is not configured for this payment processor
        """
        super(PaypalPro, self).__init__(site)

    @property
    def error_url(self):
        return get_ecommerce_url(self.configuration['error_path'])

    def get_transaction_parameters(self, basket, request=None, use_client_side_checkout=False, **kwargs):

        transaction_id = uuid.uuid4()
        return_url = urljoin(
            get_ecommerce_url(),
            reverse('paypal_pro:execute', kwargs={'transaction_id': transaction_id})
        )

        currency_code = 'currency_code={code}'.format(code=basket.currency)

        data = {
            'METHOD': "BMCreateButton",
            "BUTTONTYPE": "PAYMENT",
            "BUTTONCODE": "TOKEN",
            'L_BUTTONVAR0': 'subtotal={}'.format(unicode(basket.total_incl_tax)),
            'L_BUTTONVAR1': 'template=templateD',
            'L_BUTTONVAR2': 'return={}'.format(return_url),
            'L_BUTTONVAR3': 'notify_url={}'.format(return_url),
            'L_BUTTONVAR4': currency_code,
            'L_BUTTONVAR5': 'showHostedThankyouPage=false',
        }

        response, payment_url = self._nvp_request(**data)

        entry = self.record_processor_response(response, transaction_id=transaction_id, basket=basket)

        hosted_button_id = response.get('HOSTEDBUTTONID', None)

        if not hosted_button_id:
            logger.error(
                "HOSTEDBUTTONID missing from PayPal transaction [%s]. PayPal's response was recorded in entry [%d].",
                transaction_id,
                entry.id
            )
            raise GatewayError(
                'HOSTEDBUTTONID missing from PayPal payment response. See entry [{}] for details.'.format(entry.id)
            )

        return {
            'payment_page_url': payment_url,
            'hosted_button_id': hosted_button_id,
        }

    def handle_processor_response(self, response, basket=None):

        transaction_id = response.get('transaction_id')

        self.update_processor_response(transaction_id, response)

        if self.verify_transaction(response):

            currency = response.get('mc_currency')
            total = response.get('mc_gross')

            logger.info("Successfully executed PayPal payment [%s] for basket [%d].", transaction_id, basket.id)

            email = response.get('payer_email')
            label = 'PayPal ({})'.format(email) if email else 'PayPal Account'

            return HandledProcessorResponse(
                transaction_id=transaction_id,
                total=total,
                currency=currency,
                card_number=label,
                card_type=None
            )
        raise PaymentError

    def issue_credit(self, order_number, basket, reference_number, amount, currency):
        pass

    def update_processor_response(self, transaction_id, response):
        """
        """
        PaymentProcessorResponse.objects.filter(
            processor_name=self.NAME,
            transaction_id=transaction_id
        ).update(response=response)

    def verify_transaction(self, response):
        """
        """
        tx = response.get('txn_id')
        if not tx:
            return None
        data = {
            'METHOD': "GetTransactionDetails",
            "TRANSACTIONID": tx
        }

        nvp_response, url = self._nvp_request(**data)

        if not response.get('mc_gross'):
            response['mc_gross'] = nvp_response.get('AMT')
            response['mc_currency'] = nvp_response.get('CURRENCYCODE')

        return nvp_response.get('PAYMENTSTATUS') == 'Completed'

    def _nvp_request(self, **kwargs):

        nvp_data = self.configuration.copy()

        nvp_data.update(kwargs)

        mode = nvp_data.get('mode')

        if mode == 'sandbox':
            nvp_url = 'https://api-3t.sandbox.paypal.com/nvp'
            payment_url = 'https://securepayments.sandbox.paypal.com/webapps/HostedSoleSolutionApp/webflow/sparta/hostedSoleSolutionProcess'
        else:
            nvp_url = 'https://api-3t.paypal.com/nvp'
            payment_url = 'https://securepayments.paypal.com/webapps/HostedSoleSolutionApp/webflow/sparta/hostedSoleSolutionProcess'

        response = requests.post(nvp_url, data=nvp_data).content

        return QueryDict(response, encoding='UTF-8').dict(), payment_url

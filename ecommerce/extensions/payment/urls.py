from django.conf.urls import include, url

from ecommerce.extensions.payment.views import PaymentFailedView, SDNFailure, cybersource, paypal, stripe, paypal_pro

TRANSACTION_ID_PATTERN = r'(?P<transaction_id>[a-f\d-]+)'

CYBERSOURCE_APPLE_PAY_URLS = [
    url(r'^authorize/$', cybersource.CybersourceApplePayAuthorizationView.as_view(), name='authorize'),
    url(r'^start-session/$', cybersource.ApplePayStartSessionView.as_view(), name='start_session'),
]
CYBERSOURCE_URLS = [
    url(r'^apple-pay/', include(CYBERSOURCE_APPLE_PAY_URLS, namespace='apple_pay')),
    url(r'^redirect/$', cybersource.CybersourceInterstitialView.as_view(), name='redirect'),
    url(r'^submit/$', cybersource.CybersourceSubmitView.as_view(), name='submit'),
]

PAYPAL_URLS = [
    url(r'^execute/$', paypal.PaypalPaymentExecutionView.as_view(), name='execute'),
    url(r'^profiles/$', paypal.PaypalProfileAdminView.as_view(), name='profiles'),
]

SDN_URLS = [
    url(r'^failure/$', SDNFailure.as_view(), name='failure'),
]

STRIPE_URLS = [
    url(r'^submit/$', stripe.StripeSubmitView.as_view(), name='submit'),
]

PAYPAL_PRO_URLS = [
    url(
        r'^execute/{transaction_id}$'.format(
            transaction_id=TRANSACTION_ID_PATTERN,
        ),
        paypal_pro.PaypalProPaymentExecutionView.as_view(),
        name='execute'
    ),
    url(
        r'^ipn/{transaction_id}$'.format(
            transaction_id=TRANSACTION_ID_PATTERN,
        ),
        paypal_pro.PaypalProNotificationView.as_view(),
        name='ipn'
    ),
]

urlpatterns = [
    url(r'^cybersource/', include(CYBERSOURCE_URLS, namespace='cybersource')),
    url(r'^error/$', PaymentFailedView.as_view(), name='payment_error'),
    url(r'^paypal/', include(PAYPAL_URLS, namespace='paypal')),
    url(r'^sdn/', include(SDN_URLS, namespace='sdn')),
    url(r'^stripe/', include(STRIPE_URLS, namespace='stripe')),
    url(r'^paypal-pro/', include(PAYPAL_PRO_URLS, namespace='paypal_pro')),
]

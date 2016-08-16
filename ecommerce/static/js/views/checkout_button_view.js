define([
        'jquery',
        'underscore',
        'backbone',
        'js-cookie'
    ],
    function ($,
              _,
              Backbone,
              Cookies
    ) {
        'use strict';

        return Backbone.View.extend({
            events: {
                'click .payment-button': 'checkout'
            },

            initialize: function () {
                this.$paymentForm = $('<form>', {
                    class: 'hidden',
                    method: 'POST',
                    'accept-method': 'UTF-8'
                }).appendTo(this.$el);
            },

            checkout: function (event) {
                var $target = $(event.currentTarget),
                    url = '/api/v2/checkout/',
                    postData = JSON.stringify({
                        basket_id: this.$el.data('basket-id'),
                        payment_processor: $target.data('processor-name')
                    });

                // Disable the payment button to prevent multiple submissions
                this.setPaymentEnabled(false);

                $.ajax({
                    url: url,
                    method: 'post',
                    contentType: 'application/json',
                    data: postData,
                    headers: {'X-CSRFToken': Cookies.get('ecommerce_csrftoken')},
                    context: this,
                    success: this.handleCheckoutResponse,
                    error: this.handleCheckoutError
                });
            },

            setPaymentEnabled: function (isEnabled) {
                if (_.isUndefined(isEnabled)) {
                    isEnabled = true;
                }
                $('.payment-button')
                    .toggleClass('is-disabled', !isEnabled)
                    .prop('disabled', !isEnabled)
                    .attr('aria-disabled', !isEnabled);
            },

            handleCheckoutResponse: function (paymentDataResponse) {
                // At this point, the basket has been frozen on the server,
                // and we've received signed payment parameters.
                // We need to dynamically construct a form using
                // these parameters, then submit it to the payment processor.
                // This will send the user to an externally-hosted page
                // where she can proceed with payment.
                var self = this,
                    paymentData = paymentDataResponse.payment_form_data,
                    paymentUrl = paymentDataResponse.payment_page_url;

                $('input', this.$paymentForm).remove();

                this.$paymentForm.attr('action', paymentUrl);

                _.each(paymentData, function (value, key) {
                    $('<input>').attr({
                        type: 'hidden',
                        name: key,
                        value: value
                    }).appendTo(self.$paymentForm);
                });

                this.submitForm(this.$paymentForm);
            },

            submitForm: function (form) {
                form.submit();
            },

            handleCheckoutError: function (xhr) {
                var errorMsg = gettext('An error has occurred. Please try again.');

                if (xhr.status === 400) {
                    errorMsg = xhr.responseText;
                }

                 $('#messages').empty().append(
                    '<div class="alert alert-danger fade in" role="alert">' +
                    '<a class="close" data-dismiss="alert" href="#">' +
                    '<span aria-hidden="true">×</span>' +
                    '<span class="sr-only">Close</span>' +
                    '</a>' +
                    '<div class="alertinner wicon">' +
                    errorMsg +
                    '</div>' +
                    '</div>'
                );

                // Re-enable the button so the user can re-try
                this.setPaymentEnabled(true);
            }
        });
    });
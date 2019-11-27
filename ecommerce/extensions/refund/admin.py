import waffle
from django.contrib import admin, messages
from django.utils.translation import ugettext_lazy as _
from oscar.core.loading import get_model

from ecommerce.extensions.refund.constants import REFUND_LIST_VIEW_SWITCH

Refund = get_model('refund', 'Refund')
RefundLine = get_model('refund', 'RefundLine')


class RefundLineInline(admin.TabularInline):
    model = RefundLine
    fields = ('order_line', 'line_credit_excl_tax', 'quantity', 'status', 'created', 'modified',)
    readonly_fields = ('order_line', 'line_credit_excl_tax', 'quantity', 'created', 'modified',)
    extra = 0


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'user', 'status', 'total_credit_excl_tax', 'currency', 'created', 'modified',)
    list_filter = ('status',)
    show_full_result_count = False

    fields = ('order', 'user', 'status', 'total_credit_excl_tax', 'currency', 'created', 'modified',)
    readonly_fields = ('order', 'user', 'total_credit_excl_tax', 'currency', 'created', 'modified',)
    inlines = (RefundLineInline,)

    def get_queryset(self, request):
        if not waffle.switch_is_active(REFUND_LIST_VIEW_SWITCH):
            # Translators: "Waffle" is the name of a third-party library. It should not be translated
            msg = _('Refund administration has been disabled due to the load on the database. '
                    'This functionality can be restored by activating the {switch_name} Waffle switch. '
                    'Be careful when re-activating this switch!').format(switch_name=REFUND_LIST_VIEW_SWITCH)

            self.message_user(request, msg, level=messages.WARNING)
            return Refund.objects.none()

        queryset = super(RefundAdmin, self).get_queryset(request)
        return queryset

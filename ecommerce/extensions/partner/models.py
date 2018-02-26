from django.db import models
from django.utils.translation import ugettext_lazy as _
from oscar.apps.partner.abstract_models import AbstractPartner


class Partner(AbstractPartner):
    # short_code is the unique identifier for the 'Partner'
    short_code = models.CharField(max_length=8, unique=True, null=False, blank=False)
    enable_sailthru = models.BooleanField(default=True, verbose_name=_('Enable Sailthru Reporting'),
                                          help_text='DEPRECATED: Use SiteConfiguration!')

    class Meta(object):
        # Model name that will appear in the admin panel
        verbose_name = _('Partner')
        verbose_name_plural = _('Partners')


# noinspection PyUnresolvedReferences
from oscar.apps.partner.models import *  # noqa isort:skip pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position,ungrouped-imports

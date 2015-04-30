from oscar.core.loading import get_model
from oscar.test import factories

Category = get_model('catalogue', 'Category')
Partner = get_model('partner', 'Partner')
ProductClass = get_model('catalogue', 'ProductClass')
ProductAttribute = get_model('catalogue', 'ProductAttribute')


class CourseCatalogTestMixin(object):
    def setUp(self):
        super(CourseCatalogTestMixin, self).setUp()

        # Force the creation of a seat ProductClass
        self.seat_product_class  # pylint: disable=pointless-statement
        self.partner, _created = Partner.objects.get_or_create(code='edx')
        self.category, _created = Category.objects.get_or_create(name='Seats', defaults={'depth': 1})

    @property
    def seat_product_class(self):
        defaults = {'requires_shipping': False, 'track_stock': False, 'name': 'Seat'}
        pc, created = ProductClass.objects.get_or_create(slug='seat', defaults=defaults)

        if created:
            factories.ProductAttributeFactory(code='certificate_type', product_class=pc, type='text')
            factories.ProductAttributeFactory(code='course_key', product_class=pc, type='text')
            factories.ProductAttributeFactory(code='id_verification_required', product_class=pc, type='boolean')

        return pc

    def create_course_seats(self, course_id, certificate_types):
        title = 'Seat in {}'.format(course_id)
        parent_product = factories.ProductFactory(structure='parent', title=title,
                                                  product_class=self.seat_product_class)

        seats = {}
        for certificate_type in certificate_types:
            seat_title = '{title} with {type} certificate'.format(title=title, type=certificate_type)
            seat = factories.ProductFactory(structure='child', title=seat_title, product_class=None,
                                            parent=parent_product)

            seat.attr.certificate_type = certificate_type
            seat.attr.course_key = course_id
            seat.save()

            factories.StockRecordFactory(product=seat)

            seats[certificate_type] = seat

        return seats

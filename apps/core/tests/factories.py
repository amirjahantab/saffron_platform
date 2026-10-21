from decimal import Decimal
from apps.accounts.models import User
from apps.catalog.models import Product, ProductVariant, PackagingType, HarvestBatch, SaffronGrade
from apps.orders.models import Cart, CartItem
from apps.orders.services.checkout_service import CheckoutService
from apps.orders.services.reservation_service import OrderStateAndReservationService
from apps.payments.models import PaymentTransaction


def catalog():
    packaging = PackagingType.objects.create(name="ظرف", slug="test-box")
    batch = HarvestBatch.objects.create(batch_code="TEST-COMPLETE-01", saffron_grade=SaffronGrade.SUPER_NEGIN, origin_region="قائنات", harvest_year=1405)
    product = Product.objects.create(name="زعفران تست", slug="completion-saffron", saffron_grade=SaffronGrade.SUPER_NEGIN, short_description="توضیح واقعی نمونه", description="متن کامل")
    variant = ProductVariant.objects.create(product=product, packaging_type=packaging, harvest_batch=batch, sku="COMPLETE-01", net_weight_grams=Decimal("1"), weight_label="۱ گرم", base_price_rial=500000, stock_quantity=20, max_order_quantity=20)
    return product, variant


def user(phone="09121110001", **kwargs):
    return User.objects.create_user(phone, **kwargs)


def paid_order(owner, variant):
    cart = Cart.objects.create(user=owner)
    CartItem.objects.create(cart=cart, variant=variant, quantity=1)
    order, _ = CheckoutService.create_order_from_cart(user=owner, address_data={"recipient_full_name": "خریدار", "recipient_phone": owner.phone_number, "province": "خراسان", "city": "مشهد", "address_line": "نشانی تست", "postal_code": "9188144556"})
    order = OrderStateAndReservationService.transition_order_status(order, "paid")
    PaymentTransaction.objects.create(order=order, status="succeeded", provider="sandbox", amount_rial=order.payable_rial, authority=f"TEST-{order.pk}", reference_id=f"REF-{order.pk}")
    return order

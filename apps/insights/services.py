import re
import secrets
from urllib.parse import urlsplit
from django.utils.crypto import salted_hmac
from .models import Event, Preference, OrderAttribution


def consent(request):
    if request.user.is_authenticated:
        return Preference.objects.filter(user=request.user, analytics=True).exists()
    return request.session.get("analytics_consent") is True


def record(request, kind, product=None):
    if not consent(request):
        return
    from apps.core.limits import enforce_limit
    token = request.session.get("analytics_token")
    if not token:
        token = secrets.token_hex(16)
        request.session["analytics_token"] = token
    visitor = salted_hmac("analytics", token).hexdigest()
    if not enforce_limit("analytics:" + visitor, 120, 60):
        return
    def clean(value):
        return re.sub(r"[^a-zA-Z0-9_.-]", "", value)[:64]
    source = clean(request.GET.get("utm_source", ""))
    campaign = clean(request.GET.get("utm_campaign", ""))
    if source:
        request.session["traffic_source"] = source
        request.session["traffic_campaign"] = campaign
    elif not request.session.get("traffic_source"):
        try:
            referring_host = urlsplit(request.META.get("HTTP_REFERER", "")).hostname or "direct"
        except ValueError:
            referring_host = "direct"
        request.session["traffic_source"] = clean(referring_host)
    return Event.objects.create(kind=kind, visitor=visitor, product=product,
        source=request.session.get("traffic_source", "direct"), campaign=request.session.get("traffic_campaign", ""))


def attach_order(request, order):
    event = record(request, "checkout")
    if event:
        attribution, created = OrderAttribution.objects.get_or_create(order=order, defaults={"visitor": event.visitor, "source": event.source, "campaign": event.campaign})
        if created:
            event.order = order
            event.save(update_fields=["order"])
        else:
            event.delete()


def revenue_report():
    from django.db.models import Sum, Count, F
    from apps.orders.models import OrderItem, Order
    from apps.payments.models import PaymentRefund
    # Paid is authoritative even when the order subsequently ships or is refunded.
    paid = Order.objects.filter(paid_at__isnull=False)
    gross = paid.aggregate(amount=Sum("payable_rial"))["amount"] or 0
    refunds = PaymentRefund.objects.filter(status="succeeded").aggregate(amount=Sum("amount_rial"))["amount"] or 0
    products = OrderItem.objects.filter(order__paid_at__isnull=False).values("variant__product__name").annotate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_effective_price_rial"))).order_by("-revenue")[:20]
    return {"paid_orders": paid.count(), "gross_rial": gross, "refunds_rial": refunds, "net_rial": gross-refunds,
        "funnel": behavioral_funnel(), "products": products,
        "sources": Event.objects.exclude(source="").values("source", "campaign").annotate(count=Count("pk")).order_by("-count")[:20]}


def behavioral_funnel():
    from django.db.models import Count, Q
    stages = ["product_view", "add_to_cart", "checkout", "purchase"]
    visitors = Event.objects.exclude(visitor="").values("visitor").annotate(**{kind: Count("pk", filter=Q(kind=kind)) for kind in stages})
    result = []
    previous = None
    for stage in stages:
        visitors = visitors.filter(**{stage+"__gt": 0})
        count = visitors.count()
        dropoff = ((previous-count)*100//previous) if previous else 0
        result.append({"kind": stage, "count": count, "dropoff_percent": dropoff})
        previous = count
    return result

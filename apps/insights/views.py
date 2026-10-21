from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .models import Preference
from .services import revenue_report


@never_cache
@require_http_methods(["GET", "POST"])
def preferences(request):
    current = Preference.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    if request.method == "POST":
        analytics = request.POST.get("analytics") == "on"
        marketing = request.POST.get("marketing") == "on"
        if request.user.is_authenticated:
            Preference.objects.update_or_create(user=request.user, defaults={"analytics": analytics, "marketing": marketing})
        request.session["analytics_consent"] = analytics
        if not analytics:
            from .models import Event
            from django.utils.crypto import salted_hmac
            token = request.session.pop("analytics_token", None)
            if token:
                Event.objects.filter(visitor=salted_hmac("analytics", token).hexdigest()).delete()
                from .models import OrderAttribution
                OrderAttribution.objects.filter(visitor=salted_hmac("analytics", token).hexdigest()).delete()
            if request.user.is_authenticated:
                from .models import OrderAttribution
                OrderAttribution.objects.filter(order__user=request.user).delete()
            request.session.pop("traffic_source", None)
            request.session.pop("traffic_campaign", None)
        messages.success(request, "انتخاب‌های حریم خصوصی شما ذخیره شد.")
        return redirect("insights:preferences")
    return render(request, "insights/preferences.html", {"preferences": current, "analytics": current.analytics if current else request.session.get("analytics_consent", False), "page_title": "حریم خصوصی و ترجیحات"})


@never_cache
@staff_member_required
@permission_required("insights.view_event", raise_exception=True)
def dashboard(request):
    return render(request, "insights/dashboard.html", {"report": revenue_report(), "page_title": "گزارش فروش و مسیر خرید"})

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin
from redis.exceptions import RedisError
from .client_ip import client_ip
from .limits import enforce_limit


class SensitiveActionMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST":
            return None
        name = request.resolver_match.view_name
        if name in {"storefront:checkout_page", "storefront:guest_checkout", "orders:checkout"} and not settings.DEMO_MODE and not settings.STORE_OPEN:
            message = "ثبت سفارش هنوز آغاز نشده است. برای دریافت اطلاعات به پشتیبانی پیام بدهید."
            if name.startswith("orders:"):
                return JsonResponse({"status": "error", "message": message}, status=503)
            return render(request, "errors/rate_limit.html", {"message": message, "page_title": "ثبت سفارش موقتاً بسته است"}, status=503)
        if not settings.ENABLE_ACTION_LIMITS:
            return None
        budget = settings.ACTION_LIMITS.get(name)
        if not budget:
            return None
        identity = f"user:{request.user.pk}" if request.user.is_authenticated else "ip:" + client_ip(request)
        key = salted_hmac("action-limit", identity+":"+name).hexdigest()
        maximum, window = budget
        status = 429
        try:
            if enforce_limit(key, maximum, window):
                return None
        except RedisError:
            status = 503
        message = "تعداد درخواست‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." if status == 429 else "سرویس موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید."
        if request.content_type == "application/json" or name.startswith(("orders:", "payments:")):
            response = JsonResponse({"status": "error", "message": message}, status=status)
        else:
            response = render(request, "errors/rate_limit.html", {"message": message, "page_title": "لطفاً کمی صبر کنید"}, status=status)
        response.headers["Retry-After"] = str(window)
        return response

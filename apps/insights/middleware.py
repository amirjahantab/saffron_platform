from .services import record


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = request.resolver_match
        if request.method == "GET" and response.status_code == 200 and match:
            if match.view_name == "storefront:product_detail":
                from apps.catalog.models import Product
                record(request, "product_view", Product.objects.filter(slug=match.kwargs["slug"], is_active=True).first())
            elif match.view_name == "storefront:product_list" and request.GET.get("q"):
                record(request, "search")  # Search text is deliberately never retained.
            elif match.view_name == "storefront:checkout_page":
                record(request, "checkout")
        return response

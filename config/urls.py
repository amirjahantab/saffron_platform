"""Root URL configuration for Saffron E-commerce Platform."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.storefront.search_views import robots, sitemap_index, sitemap_section
from apps.catalog.document_views import block_raw_documents

urlpatterns = [
    path("media/catalog/certificates/<path:path>", block_raw_documents),
    path("", include("apps.assistant.urls", namespace="assistant")),
    path("", include("apps.content.urls", namespace="content")),
    path("", include("apps.care.urls", namespace="care")),
    path("", include("apps.insights.urls", namespace="insights")),
    path("robots.txt", robots, name="robots"),
    path("sitemap.xml", sitemap_index, name="sitemap-index"),
    path("sitemap-<str:section>.xml", sitemap_section, name="sitemap-section"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("orders/", include("apps.orders.urls", namespace="orders")),
    path("payments/", include("apps.payments.urls", namespace="payments")),
    path("", include("apps.core.urls", namespace="core")),
    path("", include("apps.storefront.urls", namespace="storefront")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

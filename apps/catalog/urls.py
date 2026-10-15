"""URL routing for catalog and laboratory data endpoints."""
from django.urls import path
from apps.catalog.views import product_detail_view, product_list_view

app_name = "catalog"

urlpatterns = [
    path("products/", product_list_view, name="product_list"),
    path("products/<str:slug>/", product_detail_view, name="product_detail"),
]
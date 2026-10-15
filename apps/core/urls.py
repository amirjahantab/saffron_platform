"""URL routing for core infrastructure endpoints."""
from django.urls import path
from apps.core.views import health_check_view

app_name = "core"

urlpatterns = [
    path("health/", health_check_view, name="health_check"),
]
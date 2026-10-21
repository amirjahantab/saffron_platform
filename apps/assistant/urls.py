from django.urls import path
from . import views
app_name = "assistant"
urlpatterns = [path("assistant/", views.page, name="page"), path("assistant/ask/", views.ask, name="ask")]

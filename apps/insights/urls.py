from django.urls import path
from . import views
app_name = "insights"
urlpatterns = [path("preferences/", views.preferences, name="preferences"), path("staff/insights/", views.dashboard, name="dashboard")]

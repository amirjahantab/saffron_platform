from django.urls import path
from . import views
app_name = "care"
urlpatterns = [path("support/", views.inbox, name="inbox"), path("support/<uuid:public_id>/", views.ticket, name="ticket"), path("reviews/<str:slug>/", views.review, name="review")]

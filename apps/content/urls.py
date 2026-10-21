from django.urls import path
from . import views

app_name = "content"
urlpatterns = [path("journal/", views.journal, name="journal"), path("journal/<str:slug>/", views.article, name="article"), path("pages/<slug:slug>/", views.policy, name="policy"), path("faq/", views.faq, name="faq")]

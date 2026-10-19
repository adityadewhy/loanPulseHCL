from django.urls import path
from . import views

urlpatterns = [path("kpis", views.dashboard, name="dashboard")]

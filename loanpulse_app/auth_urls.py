from django.urls import path
from . import views

urlpatterns = [
    path("login", views.login, name="login"),
    path("signup", views.signup, name="signup"),
    path("staff-registrations", views.staff_registrations, name="staff-registrations"),
    path("me", views.me, name="me"),
]

from django.urls import path
from . import views

urlpatterns = [
    path("", views.notifications, name="notifications"),
    path("unread-count", views.unread_count, name="unread-count"),
    path("<int:notification_id>/read", views.mark_notification_read, name="notification-read"),
]

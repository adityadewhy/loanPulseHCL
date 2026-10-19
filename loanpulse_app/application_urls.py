from django.urls import path
from . import views

urlpatterns = [
    path("", views.applications, name="applications"),
    path("count", views.application_count, name="application-count"),
    path("<int:loan_id>/details", views.application_details, name="application-details"),
    path("<int:loan_id>/status", views.application_status, name="application-status"),
    path("<int:loan_id>/audit", views.application_audit, name="application-audit"),
    path("<int:loan_id>/documents", views.loan_documents, name="loan-documents"),
    path("<int:loan_id>", views.application_details, name="application"),
]

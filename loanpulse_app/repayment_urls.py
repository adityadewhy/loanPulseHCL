from django.urls import path
from . import views

urlpatterns = [
    path("overdue/all", views.overdue_installments, name="overdue-installments"),
    path("batch/trigger-overdue-check", views.trigger_overdue_check, name="trigger-overdue-check"),
    path("<int:loan_id>/export-csv", views.export_schedule, name="export-schedule"),
    path("<int:loan_id>/pay/<int:installment_id>", views.record_payment, name="record-payment"),
    path("<int:loan_id>", views.repayment_schedule, name="repayment-schedule"),
]

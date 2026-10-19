from django.urls import path
from . import views

urlpatterns = [path("", views.disbursements, name="disbursements"), path("<int:loan_id>", views.disbursement_detail, name="disbursement-detail")]

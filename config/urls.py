from django.urls import include, path
from loanpulse_app.views import frontend, health, karzai_chat, karzai_kyc_review

urlpatterns = [
    path("", frontend, name="frontend"),
    path("health", health, name="health"),
    path("karzai/chat", karzai_chat, name="karzai-chat"),
    path("karzai/documents/<int:document_id>/review", karzai_kyc_review, name="karzai-kyc-review"),
    path("auth/", include("loanpulse_app.auth_urls")),
    path("applications/", include("loanpulse_app.application_urls")),
    path("disbursements/", include("loanpulse_app.disbursement_urls")),
    path("repayments/", include("loanpulse_app.repayment_urls")),
    path("dashboard/", include("loanpulse_app.dashboard_urls")),
    path("notifications/", include("loanpulse_app.notification_urls")),
    path("documents/", include("loanpulse_app.document_urls")),
]

from django.urls import path
from . import views

urlpatterns = [
    path("<int:document_id>/download", views.document_download, name="document-download"),
    path("<int:document_id>", views.document_delete, name="document-delete"),
]

from django.urls import path

from .views import DocumentDetailView, DocumentDownloadView

urlpatterns = [
    path('/<uuid:pk>', DocumentDetailView.as_view(), name='document-detail'),
    path('/<uuid:pk>/', DocumentDetailView.as_view(), name='document-detail-slash'),
    path('/<uuid:pk>/download', DocumentDownloadView.as_view(), name='document-download'),
    path('/<uuid:pk>/download/', DocumentDownloadView.as_view(), name='document-download-slash'),
]

from django.urls import path

from .views import ReportDetailView, ReportDownloadView

urlpatterns = [
    path('/<uuid:pk>', ReportDetailView.as_view(), name='report-detail'),
    path('/<uuid:pk>/', ReportDetailView.as_view(), name='report-detail-slash'),
    path('/<uuid:pk>/download', ReportDownloadView.as_view(), name='report-download'),
    path('/<uuid:pk>/download/', ReportDownloadView.as_view(), name='report-download-slash'),
]

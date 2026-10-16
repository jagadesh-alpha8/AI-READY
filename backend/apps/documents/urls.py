from django.urls import path

from .views import DocumentConfirmCategoryView, DocumentDetailView, DocumentDownloadView

urlpatterns = [
    path('/<uuid:pk>', DocumentDetailView.as_view(), name='document-detail'),
    path('/<uuid:pk>/', DocumentDetailView.as_view(), name='document-detail-slash'),
    path('/<uuid:pk>/download', DocumentDownloadView.as_view(), name='document-download'),
    path('/<uuid:pk>/download/', DocumentDownloadView.as_view(), name='document-download-slash'),
    path('/<uuid:pk>/confirm-category', DocumentConfirmCategoryView.as_view(), name='document-confirm-category'),
    path(
        '/<uuid:pk>/confirm-category/', DocumentConfirmCategoryView.as_view(),
        name='document-confirm-category-slash',
    ),
]

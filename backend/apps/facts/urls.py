from django.urls import path

from .views import FactConfirmView, FactCorrectView, FactDetailView, FactRejectView, FactRequestEvidenceView

urlpatterns = [
    path('/<uuid:pk>', FactDetailView.as_view(), name='fact-detail'),
    path('/<uuid:pk>/', FactDetailView.as_view(), name='fact-detail-slash'),
    path('/<uuid:pk>/confirm', FactConfirmView.as_view(), name='fact-confirm'),
    path('/<uuid:pk>/confirm/', FactConfirmView.as_view(), name='fact-confirm-slash'),
    path('/<uuid:pk>/correct', FactCorrectView.as_view(), name='fact-correct'),
    path('/<uuid:pk>/correct/', FactCorrectView.as_view(), name='fact-correct-slash'),
    path('/<uuid:pk>/reject', FactRejectView.as_view(), name='fact-reject'),
    path('/<uuid:pk>/reject/', FactRejectView.as_view(), name='fact-reject-slash'),
    path('/<uuid:pk>/request-evidence', FactRequestEvidenceView.as_view(), name='fact-request-evidence'),
    path(
        '/<uuid:pk>/request-evidence/',
        FactRequestEvidenceView.as_view(),
        name='fact-request-evidence-slash',
    ),
]

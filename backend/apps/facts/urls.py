from django.urls import path

from .views import (
    FactAIQIFMappingAddView,
    FactAIQIFMappingEditView,
    FactAIQIFMappingReopenView,
    FactAIQIFMappingReviewView,
    FactKindView,
    FactAssignView,
    FactConfirmView,
    FactCorrectView,
    FactDetailView,
    FactRejectView,
    FactRequestEvidenceView,
)

urlpatterns = [
    path('/<uuid:pk>/assign', FactAssignView.as_view(), name='fact-assign'),
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
    path('/<uuid:pk>/aiqif-mappings/<str:indicator_code>/review', FactAIQIFMappingReviewView.as_view(),
         name='fact-aiqif-mapping-review'),
    path('/<uuid:pk>/aiqif-mappings', FactAIQIFMappingAddView.as_view(), name='fact-aiqif-mapping-add'),
    path('/<uuid:pk>/aiqif-mappings/<str:indicator_code>/edit', FactAIQIFMappingEditView.as_view(),
         name='fact-aiqif-mapping-edit'),
    path('/<uuid:pk>/aiqif-mappings/<str:indicator_code>/reopen', FactAIQIFMappingReopenView.as_view(),
         name='fact-aiqif-mapping-reopen'),
    path('/<uuid:pk>/fact-kind', FactKindView.as_view(), name='fact-kind'),
]

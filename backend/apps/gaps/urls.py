from django.urls import path

from .views import (
    GapChooseConflictValueView,
    GapAssignView, GapDetailView, GapMarkUnavailableView, GapResolveView, GapSkipView, GapUploadEvidenceView,
)

urlpatterns = [
    path('/<uuid:pk>', GapDetailView.as_view(), name='gap-detail'),
    path('/<uuid:pk>/', GapDetailView.as_view(), name='gap-detail-slash'),
    path('/<uuid:pk>/assign', GapAssignView.as_view(), name='gap-assign'),
    path('/<uuid:pk>/choose-value', GapChooseConflictValueView.as_view(), name='gap-choose-value'),
    path('/<uuid:pk>/upload-evidence', GapUploadEvidenceView.as_view(), name='gap-upload-evidence'),
    path('/<uuid:pk>/resolve', GapResolveView.as_view(), name='gap-resolve'),
    path('/<uuid:pk>/resolve/', GapResolveView.as_view(), name='gap-resolve-slash'),
    path('/<uuid:pk>/mark-unavailable', GapMarkUnavailableView.as_view(), name='gap-mark-unavailable'),
    path(
        '/<uuid:pk>/mark-unavailable/',
        GapMarkUnavailableView.as_view(),
        name='gap-mark-unavailable-slash',
    ),
    path('/<uuid:pk>/skip', GapSkipView.as_view(), name='gap-skip'),
    path('/<uuid:pk>/skip/', GapSkipView.as_view(), name='gap-skip-slash'),
]

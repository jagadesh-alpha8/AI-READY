from django.urls import path

from .verification_views import CorrectionApproveView, CorrectionRejectView, CorrectionWithdrawView

urlpatterns = [
    path('/<uuid:pk>/approve', CorrectionApproveView.as_view(), name='fact-correction-approve'),
    path('/<uuid:pk>/reject', CorrectionRejectView.as_view(), name='fact-correction-reject'),
    path('/<uuid:pk>/withdraw', CorrectionWithdrawView.as_view(), name='fact-correction-withdraw'),
]

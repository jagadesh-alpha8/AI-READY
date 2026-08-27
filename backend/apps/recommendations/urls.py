from django.urls import path

from .views import RecommendationDetailView

urlpatterns = [
    path('/<uuid:pk>', RecommendationDetailView.as_view(), name='recommendation-detail'),
    path('/<uuid:pk>/', RecommendationDetailView.as_view(), name='recommendation-detail-slash'),
]

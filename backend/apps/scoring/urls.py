from django.urls import path

from .views import ScoringConfigView

urlpatterns = [
    path('/config', ScoringConfigView.as_view(), name='scoring-config'),
]

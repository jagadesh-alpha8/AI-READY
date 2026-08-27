from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ChangePasswordView, LoginView, LogoutView, MeView

# Registered both with and without a trailing slash: the task spec documents
# these as .../login/ etc., but APPEND_SLASH=False (see settings) and the
# existing frontend's axios client calls them without a trailing slash
# (e.g. '/auth/login'). Both forms resolve to the same view.
urlpatterns = [
    path('login', LoginView.as_view(), name='login'),
    path('login/', LoginView.as_view(), name='login-slash'),
    path('refresh', TokenRefreshView.as_view(), name='token-refresh'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh-slash'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('logout/', LogoutView.as_view(), name='logout-slash'),
    path('me', MeView.as_view(), name='me'),
    path('me/', MeView.as_view(), name='me-slash'),
    path('change-password', ChangePasswordView.as_view(), name='change-password'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password-slash'),
]

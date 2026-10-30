from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.institutions.views import InvitationAcceptView, InvitationCheckView

from .guide_views import (
    GuideDismissView,
    GuideResetView,
    GuideSkipView,
    GuideStatusView,
    MenuTourUpdateView,
)
from .password_reset import PasswordResetConfirmView, PasswordResetRequestView
from .role_matrix import RoleAccessMatrixView
from .views import ChangePasswordView, LoginView, LogoutView, MeView

# Registered both with and without a trailing slash: the task spec documents
# these as .../login/ etc., but APPEND_SLASH=False (see settings) and the
# existing frontend's axios client calls them without a trailing slash
# (e.g. '/auth/login'). Both forms resolve to the same view.
urlpatterns = [
    # IQAC Coordinator invitation link (apps/institutions/coordinator.py).
    path('invitation', InvitationCheckView.as_view(), name='invitation-check'),
    path('invitation/accept', InvitationAcceptView.as_view(), name='invitation-accept'),
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
    path('password-reset', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-slash'),
    path('password-reset/confirm', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-slash'),
    path('access-matrix', RoleAccessMatrixView.as_view(), name='access-matrix'),
    path('access-matrix/', RoleAccessMatrixView.as_view(), name='access-matrix-slash'),
    path('guide-status', GuideStatusView.as_view(), name='guide-status'),
    path('guide-status/', GuideStatusView.as_view(), name='guide-status-slash'),
    path('guide-skip', GuideSkipView.as_view(), name='guide-skip'),
    path('guide-skip/', GuideSkipView.as_view(), name='guide-skip-slash'),
    path('guide-dismiss', GuideDismissView.as_view(), name='guide-dismiss'),
    path('guide-dismiss/', GuideDismissView.as_view(), name='guide-dismiss-slash'),
    path('guide-reset', GuideResetView.as_view(), name='guide-reset'),
    path('guide-reset/', GuideResetView.as_view(), name='guide-reset-slash'),
    path('menu-tour-update', MenuTourUpdateView.as_view(), name='menu-tour-update'),
    path('menu-tour-update/', MenuTourUpdateView.as_view(), name='menu-tour-update-slash'),
]

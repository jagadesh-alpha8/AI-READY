from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .guide_service import (
    STEP_CONFIGS,
    get_guide_status,
    reset_guide,
    set_guide_dismissed,
    skip_guide_step,
    update_menu_tour,
)

def project_guide(request, data):
    workflow = request.query_params.get('workflow') if request.method == 'GET' else request.data.get('workflow')
    if workflow == 'capability':
        from apps.scoring.capability.guide import capability_guide
        return capability_guide(data, request.user)
    return data


VALID_STEP_IDS = {cfg['id'] for cfg in STEP_CONFIGS}


def _parse_bool(val, default=True):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() not in ('false', '0', 'no', 'f', '')
    return bool(val)


class GuideStatusView(APIView):
    """GET /api/v1/auth/guide-status
    
    Derives onboarding guide step progression from real database state.
    Scoped by user, institution, and currently selected sprint.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=None)
    def get(self, request):
        sprint_id = request.query_params.get('sprint_id') or None
        institution_id = request.query_params.get('institution_id') or None
        data = get_guide_status(request.user, sprint_id=sprint_id, institution_id=institution_id)
        return Response(project_guide(request, data), status=status.HTTP_200_OK)


class GuideSkipView(APIView):
    """POST /api/v1/auth/guide-skip
    
    Marks a guide step as Skipped or resumes it.
    Does NOT modify any underlying platform business data.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=None)
    def post(self, request):
        step_id = request.data.get('step_id')
        if not step_id or step_id not in VALID_STEP_IDS:
            return Response(
                {'detail': f'Valid step_id required. Must be one of: {sorted(list(VALID_STEP_IDS))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sprint_id = request.data.get('sprint_id') or None
        institution_id = request.data.get('institution_id') or None
        skipped = _parse_bool(request.data.get('skipped'), default=True)

        data = skip_guide_step(
            request.user,
            step_id=step_id,
            sprint_id=sprint_id,
            institution_id=institution_id,
            skipped=skipped,
        )
        return Response(project_guide(request, data), status=status.HTTP_200_OK)


class GuideDismissView(APIView):
    """POST /api/v1/auth/guide-dismiss
    
    Sets whether the compact guide card is dismissed.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=None)
    def post(self, request):
        dismissed = _parse_bool(request.data.get('dismissed'), default=True)
        sprint_id = request.data.get('sprint_id') or None
        institution_id = request.data.get('institution_id') or None

        data = set_guide_dismissed(
            request.user,
            dismissed=dismissed,
            sprint_id=sprint_id,
            institution_id=institution_id,
        )
        return Response(project_guide(request, data), status=status.HTTP_200_OK)


class GuideResetView(APIView):
    """POST /api/v1/auth/guide-reset
    
    Resets all skipped steps and un-dismisses the guide.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=None)
    def post(self, request):
        sprint_id = request.data.get('sprint_id') or None
        institution_id = request.data.get('institution_id') or None

        data = reset_guide(
            request.user,
            sprint_id=sprint_id,
            institution_id=institution_id,
        )
        return Response(project_guide(request, data), status=status.HTTP_200_OK)


class MenuTourUpdateView(APIView):
    """POST /api/v1/auth/menu-tour-update

    Records that a user has started, completed, or dismissed a contextual tour for a menu.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=None)
    def post(self, request):
        menu_key = request.data.get('menu_key')
        if not menu_key or not isinstance(menu_key, str):
            return Response({'detail': 'Valid menu_key is required.'}, status=status.HTTP_400_BAD_REQUEST)

        tour_status = request.data.get('status', 'completed')
        if tour_status not in ('completed', 'dismissed', 'in_progress', 'reset'):
            return Response(
                {'detail': "status must be one of: 'completed', 'dismissed', 'in_progress', 'reset'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sprint_id = request.data.get('sprint_id') or None
        institution_id = request.data.get('institution_id') or None

        data = update_menu_tour(
            request.user,
            menu_key=menu_key,
            status=tour_status,
            sprint_id=sprint_id,
            institution_id=institution_id,
        )
        return Response(project_guide(request, data), status=status.HTTP_200_OK)

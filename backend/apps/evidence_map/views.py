from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint
from apps.sprints.access import get_authorized_sprint

from .status import status


class MapStatusView(APIView):
    """The sprint's evidence map: how much is tagged, whether a pass is running, and the warning the Assessment page
    shows before "Run the assessment" (never blocking)."""
    permission_classes = [CanManageSprint]

    def get(self, request, sprint_id):
        return Response(status(get_authorized_sprint(request.user, sprint_id)))

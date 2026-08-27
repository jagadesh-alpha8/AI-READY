from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanEditRecommendation, CanManageRecommendations, IsInstitutionMember
from apps.sprints.access import get_authorized_sprint

from .models import Recommendation
from .serializers import RecommendationSerializer, RecommendationUpdateSerializer
from .services import generate_recommendations_for_sprint


class SprintRecommendationListView(APIView):
    """GET the sprint's current recommendations. POST also still runs the
    engine here (in addition to the dedicated .../generate/ endpoint below)
    since that's the URL the existing, unmodified frontend already posts to
    for its "Generate Recommendations" button."""
    permission_classes = [CanManageRecommendations]

    @extend_schema(responses=RecommendationSerializer(many=True))
    def get(self, request, sprint_id):
        get_authorized_sprint(request.user, sprint_id)
        recommendations = Recommendation.objects.filter(sprint_id=sprint_id)
        return Response(RecommendationSerializer(recommendations, many=True).data)

    @extend_schema(request=None, responses=RecommendationSerializer(many=True))
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        recommendations = generate_recommendations_for_sprint(sprint, triggered_by=request.user)
        return Response(RecommendationSerializer(recommendations, many=True).data, status=201)


class SprintRecommendationGenerateView(APIView):
    """POST /sprints/{sprint_id}/recommendations/generate/ -- runs the
    recommendation engine against the sprint's current gap/fact/score data.
    Same action as SprintRecommendationListView.post; a dedicated URL for
    callers that want "generate" to be explicit rather than overloading the
    list endpoint's POST verb."""
    permission_classes = [CanManageRecommendations]

    @extend_schema(request=None, responses=RecommendationSerializer(many=True))
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        recommendations = generate_recommendations_for_sprint(sprint, triggered_by=request.user)
        return Response(RecommendationSerializer(recommendations, many=True).data, status=201)


class RecommendationDetailView(generics.RetrieveUpdateAPIView):
    """GET any authorized viewer; PATCH is narrower -- only InGage
    consultants (CanEditRecommendation), not every role that can view."""
    queryset = Recommendation.objects.all()
    lookup_field = 'pk'

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [CanEditRecommendation(), IsInstitutionMember()]
        return [CanManageRecommendations(), IsInstitutionMember()]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return RecommendationUpdateSerializer
        return RecommendationSerializer

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    UserSerializer,
)
from .tokens import get_tokens_for_user


class LoginEmailThrottle(SimpleRateThrottle):
    """Limits attempts against one email address from anywhere, so spreading
    a password-guessing attack over many addresses does not get around the
    per-IP limit."""
    scope = 'login_email'

    def get_cache_key(self, request, view):
        email = str(request.data.get('email', '') if hasattr(request, 'data') else '').strip().lower()
        if not email:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': email}


class LoginView(APIView):
    permission_classes = [AllowAny]
    # Brute-force protection: per client address and per email address
    # (rates in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']).
    throttle_classes = [ScopedRateThrottle, LoginEmailThrottle]
    throttle_scope = 'login'

    @extend_schema(request=LoginSerializer, responses=LoginResponseSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        tokens = get_tokens_for_user(user)
        return Response({
            **tokens,
            'user': UserSerializer(user).data,
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer, responses=OpenApiResponse(description='Logged out'))
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RefreshToken(serializer.validated_data['refresh']).blacklist()
        except TokenError as exc:
            raise ValidationError({'refresh': str(exc)}) from exc

        return Response(status=status.HTTP_205_RESET_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_change'

    @extend_schema(request=ChangePasswordSerializer, responses=OpenApiResponse(description='Password changed'))
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Password updated successfully.'})

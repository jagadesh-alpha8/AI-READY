"""Forgot password: email a one-time link, then set a new password with it.

    POST /auth/password-reset          {email}                     -> always 200
    POST /auth/password-reset/confirm  {uid, token, new_password}  -> 200 / 400

Rules:
- The request never reveals whether an email has an account (same answer
  either way), and is rate-limited per client address and per email.
- The link carries Django's signed token: it expires after
  PASSWORD_RESET_TIMEOUT (1 hour) and stops working once the password changes,
  so it can be used once.
- The new password must pass the same validators as everywhere else.
- A successful reset signs the user out everywhere (all refresh tokens are
  blacklisted), so a stolen session does not survive it.
- Deactivated accounts never get a link.
"""
import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from .models import User

logger = logging.getLogger(__name__)

GENERIC_REPLY = ('If an account exists for that email, a link to reset the password has been sent. '
                 'It works once and expires in one hour.')


class ResetEmailThrottle(SimpleRateThrottle):
    scope = 'password_reset_email'

    def get_cache_key(self, request, view):
        email = str(request.data.get('email', '') if hasattr(request, 'data') else '').strip().lower()
        return self.cache_format % {'scope': self.scope, 'ident': email} if email else None


def reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f'{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}'


def send_reset_email(user):
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    link = reset_link(user)
    name = user.first_name or user.email
    body = (
        f'Hello {name},\n\n'
        'We received a request to reset the password of your InGage AI Readiness account.\n\n'
        f'Open this link to choose a new password (it works once and expires in {minutes} minutes):\n\n'
        f'{link}\n\n'
        'If you did not ask for this, ignore this email — your password stays the same.\n\n'
        'InGage Technologies'
    )
    html = (
        f'<p>Hello {name},</p>'
        '<p>We received a request to reset the password of your InGage AI Readiness account.</p>'
        f'<p><a href="{link}" style="background:#0f766e;color:#fff;padding:10px 16px;border-radius:6px;'
        f'text-decoration:none;display:inline-block">Choose a new password</a></p>'
        f'<p>The link works once and expires in {minutes} minutes.</p>'
        '<p>If you did not ask for this, ignore this email — your password stays the same.</p>'
        '<p>InGage Technologies</p>'
    )
    send_mail('Reset your InGage password', body, settings.DEFAULT_FROM_EMAIL, [user.email], html_message=html)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle, ResetEmailThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        email = str(request.data.get('email', '')).strip()
        if not email or '@' not in email:
            return Response({'email': ['Enter your email address.']}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            try:
                send_reset_email(user)
                logger.info('accounts.password_reset.sent user=%s', user.pk)
            except Exception as exc:  # never reveal more, never 500 -- but do log it
                logger.error('accounts.password_reset.mail_failed user=%s error=%s', user.pk, exc)
        return Response({'detail': GENERIC_REPLY})


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        try:
            pk = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=pk, is_active=True)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist, DjangoValidationError):
            user = None
        if user is None or not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError(
                {'token': ['This reset link is invalid or has expired. Ask for a new one.']})
        try:
            validate_password(attrs['new_password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})
        attrs['user'] = user
        return attrs


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data['user']
        user.set_password(ser.validated_data['new_password'])
        user.save(update_fields=['password'])
        # Sign out everywhere: every refresh token issued before the reset stops working.
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        logger.info('accounts.password_reset.done user=%s', user.pk)
        return Response({'detail': 'Your password has been changed. You can sign in now.'})

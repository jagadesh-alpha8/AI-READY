from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    """Issue a refresh/access token pair carrying non-sensitive identity claims.

    Claims added here (role, institution_id, email) let the frontend and any
    downstream service make authorization decisions from the token alone
    without a round trip to /auth/me. They deliberately exclude anything
    sensitive (password hash, phone, other PII) — SimpleJWT copies every
    claim set on the refresh token onto the access token it derives, and
    that access token is handed to the browser.
    """
    refresh = RefreshToken.for_user(user)
    refresh['email'] = user.email
    refresh['role'] = user.role
    refresh['institution_id'] = str(user.institution_id) if user.institution_id else None

    return {
        'refresh_token': str(refresh),
        'access_token': str(refresh.access_token),
    }

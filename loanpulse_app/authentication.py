from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from .models import User

ISSUER = "loanpulse"


def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(user.pk),
        "role": user.role,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=12),
    }, settings.SECRET_KEY, algorithm="HS256")


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise exceptions.AuthenticationFailed("Invalid authorization header")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], issuer=ISSUER)
            user = User.objects.get(pk=int(payload["sub"]), is_active=True)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, User.DoesNotExist):
            raise exceptions.AuthenticationFailed("Invalid or expired token")
        return user, payload

    def authenticate_header(self, request):
        return "Bearer"

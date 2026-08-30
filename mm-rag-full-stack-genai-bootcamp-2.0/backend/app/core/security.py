from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, cast

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from backend.app.core.config import Settings


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    subject: str
    email: str | None = None
    display_name: str | None = None


class AccessTokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedIdentity: ...


class Auth0JWTVerifier:
    """Validate Auth0 access tokens without trusting unverified claims."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        jwks_cache_seconds: int = 300,
        jwks_timeout_seconds: int = 5,
        signing_key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._logger = structlog.get_logger(__name__)
        if signing_key_resolver is None:
            jwks_client = PyJWKClient(
                jwks_url,
                cache_keys=True,
                lifespan=jwks_cache_seconds,
                timeout=jwks_timeout_seconds,
            )
            self._signing_key_resolver = lambda token: (
                jwks_client.get_signing_key_from_jwt(token).key
            )
        else:
            self._signing_key_resolver = signing_key_resolver

    def verify(self, token: str) -> AuthenticatedIdentity:
        try:
            signing_key = self._signing_key_resolver(token)
            claims: Mapping[str, Any] = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["aud", "exp", "iat", "iss", "sub"]},
            )
        except (InvalidTokenError, PyJWKClientError, ValueError, TypeError) as exc:
            self._logger.info("access_token_rejected", error_type=type(exc).__name__)
            raise InvalidAccessTokenError from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise InvalidAccessTokenError

        email = claims.get("email")
        display_name = claims.get("name") or claims.get("nickname")
        return AuthenticatedIdentity(
            subject=subject,
            email=email if isinstance(email, str) and email.strip() else None,
            display_name=(
                display_name if isinstance(display_name, str) and display_name.strip() else None
            ),
        )


class InvalidAccessTokenError(Exception):
    """Raised when an access token cannot be trusted."""


def build_access_token_verifier(settings: Settings) -> AccessTokenVerifier | None:
    if not settings.auth0_is_configured:
        return None
    issuer = cast(str, settings.auth0_issuer)
    audience = cast(str, settings.auth0_audience)
    jwks_url = settings.auth0_jwks_url or f"{issuer}.well-known/jwks.json"
    return Auth0JWTVerifier(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        jwks_cache_seconds=settings.auth0_jwks_cache_seconds,
        jwks_timeout_seconds=settings.auth0_jwks_timeout_seconds,
    )


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    verifier = cast(AccessTokenVerifier | None, request.app.state.access_token_verifier)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured",
        )

    try:
        return verifier.verify(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

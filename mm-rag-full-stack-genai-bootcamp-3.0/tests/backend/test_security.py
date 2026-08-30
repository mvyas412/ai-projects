from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.core.security import Auth0JWTVerifier, InvalidAccessTokenError

ISSUER = "https://example.auth0.com/"
AUDIENCE = "https://api.mm-rag.local"


@pytest.fixture(scope="module")
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_token(private_key, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "auth0|user-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": "person@example.com",
        "name": "Example Person",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def verifier(public_key) -> Auth0JWTVerifier:
    return Auth0JWTVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.example/jwks.json",
        signing_key_resolver=lambda _token: public_key,
    )


def test_valid_access_token_returns_minimal_trusted_identity(signing_keys) -> None:
    private_key, public_key = signing_keys

    identity = verifier(public_key).verify(make_token(private_key))

    assert identity.subject == "auth0|user-123"
    assert identity.email == "person@example.com"
    assert identity.display_name == "Example Person"


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "wrong-audience"},
        {"iss": "https://wrong.example/"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
def test_invalid_access_token_is_rejected(signing_keys, overrides) -> None:
    private_key, public_key = signing_keys

    with pytest.raises(InvalidAccessTokenError):
        verifier(public_key).verify(make_token(private_key, **overrides))

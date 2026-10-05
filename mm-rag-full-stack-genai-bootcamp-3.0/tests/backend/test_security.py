import base64
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib.request import Request

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


def test_deeply_nested_token_is_rejected_before_jwks_fetch(monkeypatch, capsys) -> None:
    fetches = []

    def forbidden_fetch(_client):
        fetches.append(True)
        raise AssertionError("Malformed tokens must not reach the network")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", forbidden_fetch)
    header = base64.urlsafe_b64encode(
        b'{"alg":"RS256","kid":"test-key"}'
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(b"[" * 20_000 + b"0" + b"]" * 20_000).rstrip(b"=")
    token = b".".join((header, payload, b"synthetic-signature")).decode("ascii")
    actual_verifier = Auth0JWTVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks_url="https://unused.example/jwks.json"
    )

    with pytest.raises(InvalidAccessTokenError):
        actual_verifier.verify(token)

    assert fetches == []
    assert token not in capsys.readouterr().out


def test_real_jwks_resolution_validates_signature_and_caches_key(signing_keys, monkeypatch) -> None:
    private_key, public_key = signing_keys
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    public_jwk.update(kid="test-key", use="sig", alg="RS256")
    fetches = []

    def synthetic_open(request, *, timeout):
        assert request.full_url == "https://unused.example/jwks.json"
        assert timeout == 5
        fetches.append(True)
        return BytesIO(json.dumps({"keys": [public_jwk]}).encode())

    def synthetic_opener(*handlers):
        assert handlers[0].redirect_request(
            Request("https://unused.example/jwks.json"), None, 302, "Found", {},
            "https://untrusted.example/jwks.json",
        ) is None
        return SimpleNamespace(open=synthetic_open)

    monkeypatch.setattr("urllib.request.build_opener", synthetic_opener)
    actual_verifier = Auth0JWTVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks_url="https://unused.example/jwks.json"
    )
    token = make_token(private_key)

    assert actual_verifier.verify(token).subject == "auth0|user-123"
    assert actual_verifier.verify(token).subject == "auth0|user-123"
    assert fetches == [True]


@pytest.mark.parametrize("algorithm", ["HS256", "none"])
def test_non_rs256_access_tokens_are_rejected(signing_keys, algorithm) -> None:
    _, public_key = signing_keys
    now = datetime.now(UTC)
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "synthetic", "iat": now,
         "exp": now + timedelta(minutes=5)},
        "" if algorithm == "none" else b"synthetic-hmac-secret-for-offline-test",
        algorithm=algorithm,
    )

    with pytest.raises(InvalidAccessTokenError):
        verifier(public_key).verify(token)

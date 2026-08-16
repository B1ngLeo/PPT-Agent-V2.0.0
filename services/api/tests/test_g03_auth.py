from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from instant_ppt_api.auth import ApiAuthenticationError, OidcTokenVerifier
from instant_ppt_domain.config import DomainSettings


def _settings() -> DomainSettings:
    return DomainSettings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        redis_events_url="redis://localhost/0",
        celery_broker_url="redis://localhost/1",
        sse_heartbeat_seconds=20,
        outbox_poll_seconds=0.25,
        worker_lease_seconds=30,
        app_environment="test",
        auth_mode="oidc",
        oidc_issuer="https://issuer.example/",
        oidc_audience="instant-ppt-api",
        oidc_jwks_url="https://issuer.example/jwks.json",
    )


class _SigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


class _StaticJwks:
    def __init__(self, key: object) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, _: str) -> _SigningKey:
        return _SigningKey(self._key)


def _token(private_key: object, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://issuer.example/",
        "sub": "oidc-user-1",
        "aud": "instant-ppt-api",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": "user@example.com",
        "name": "OIDC User",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_oidc_verifier_requires_signature_issuer_audience_and_time_claims() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OidcTokenVerifier(_settings())
    verifier._jwks = _StaticJwks(private_key.public_key())  # type: ignore[assignment]
    claims = verifier.verify(_token(private_key))
    assert claims.subject == "oidc-user-1"
    assert claims.email == "user@example.com"

    for invalid in (
        _token(private_key, aud="other-api"),
        _token(private_key, iss="https://attacker.example/"),
        _token(private_key, exp=datetime.now(UTC) - timedelta(minutes=1)),
    ):
        with pytest.raises(ApiAuthenticationError, match="invalid"):
            verifier.verify(invalid)


def test_oidc_verifier_rejects_algorithm_downgrade() -> None:
    verifier = OidcTokenVerifier(_settings())
    shared_secret = "shared-secret-that-is-at-least-32-bytes"
    verifier._jwks = _StaticJwks(shared_secret)  # type: ignore[assignment]
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://issuer.example/",
            "sub": "attacker",
            "aud": "instant-ppt-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        shared_secret,
        algorithm="HS256",
    )
    with pytest.raises(ApiAuthenticationError, match="invalid"):
        verifier.verify(token)

# ADR-002: Production identity provider and token exchange

- Status: accepted
- Date: 2026-08-16
- Owners: engineering, security
- Related SPEC: 6.1, 10.1

## Context

G03 needs a production identity boundary, cookie/JWT controls and an explicit local-only test identity. The deployment region and operator may change, so application code must not depend on a provider-specific SDK or proprietary claim.

## Decision

Use standards-based OIDC. The Web/BFF uses Authorization Code with PKCE and keeps browser session cookies `HttpOnly`, `Secure`, `SameSite=Lax` with CSRF protection for cookie-authenticated mutations. The API accepts only Bearer access tokens and validates signature through the configured JWKS, exact issuer and audience, required `iss/sub/aud/iat/exp`, bounded clock skew, and an explicit RSA algorithm allowlist. Provider-specific claims stop at the adapter; the fixed FastAPI context contains internal user, membership, role, and organization IDs.

`AUTH_MODE=local` is an explicit test/development adapter. It may accept `X-Dev-User-*` headers only when `APP_ENVIRONMENT` is `local` or `test`; application construction fails for local auth in staging or production. OIDC mode requires issuer, audience, and JWKS configuration and does not fall back to local identity.

The first valid identity transaction creates exactly one personal organization, owner membership, and default entitlement. A caller may select another organization only through an active membership. Cross-tenant selection and resource lookup return the same `404` surface.

## Verification

G03 strict-JWT, production fail-closed, concurrent provisioning, membership, and cross-organization API/SSE/object tests.

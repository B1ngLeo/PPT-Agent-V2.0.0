"""Identity provisioning, tenant authorization, entitlements, and audit primitives."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    AuditLog,
    Entitlement,
    IdempotencyRecord,
    Membership,
    Organization,
    UsageLedger,
    UsageReservation,
    User,
)
from instant_ppt_domain.service import (
    SYNTHETIC_ORGANIZATION_ID,
    IdempotencyConflict,
    canonical_sha256,
)

LOCAL_ISSUER = "urn:instant-ppt:local"
DEFAULT_LOCAL_SUBJECT = "local-default"
DEFAULT_LOCAL_USER_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAC"


class AuthenticationRejected(RuntimeError):
    pass


class TenantNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class IdentityClaims:
    issuer: str
    subject: str
    email: str | None
    display_name: str


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: str
    organization_id: str
    membership_id: str
    role: str
    issuer: str
    subject: str


def find_user_idempotency(
    session: Session,
    context: TenantContext,
    *,
    route: str,
    key: str,
    request_body: dict[str, Any],
) -> IdempotencyRecord | None:
    if not key or len(key) > 200:
        raise ValueError("Idempotency-Key must contain 1 to 200 characters")
    _advisory_lock(
        session,
        f"idempotency:{context.organization_id}:{context.user_id}:{route}:{key}",
    )
    row = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == context.organization_id,
            IdempotencyRecord.actor_id == context.user_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if row is not None and row.request_sha256 != canonical_sha256(request_body):
        raise IdempotencyConflict("Idempotency-Key was already used with a different body")
    return row


def store_user_idempotency(
    session: Session,
    context: TenantContext,
    *,
    route: str,
    key: str,
    request_body: dict[str, Any],
    resource_id: str,
    response_body: dict[str, Any],
    response_status: int = 200,
) -> IdempotencyRecord:
    now = datetime.now(UTC)
    row = IdempotencyRecord(
        id=new_ulid(),
        organization_id=context.organization_id,
        actor_id=context.user_id,
        actor_kind="user",
        route=route,
        idempotency_key=key,
        request_sha256=canonical_sha256(request_body),
        response_status=response_status,
        response_headers={},
        response_body=response_body,
        resource_id=resource_id,
        expires_at=now.replace(microsecond=0) + timedelta(days=7),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def _advisory_lock(session: Session, scope: str) -> None:
    key = int.from_bytes(hashlib.sha256(scope.encode("utf-8")).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _normalized_email(email: str | None) -> str | None:
    value = email.strip().lower() if email else ""
    return value or None


def _personal_name(claims: IdentityClaims) -> str:
    candidate = claims.display_name.strip() or _normalized_email(claims.email) or "Personal"
    return f"{candidate[:140]} 的工作区"


def _add_default_entitlement(session: Session, organization_id: str, now: datetime) -> Entitlement:
    entitlement = Entitlement(
        id=new_ulid(),
        organization_id=organization_id,
        plan_code="p1-default",
        max_slides_per_deck=30,
        monthly_slide_limit=300,
        max_images_per_deck=1,
        monthly_image_limit=30,
        monthly_image_cost_limit_microunits=3_000_000,
        max_concurrent_jobs=1,
        allowed_modes=["native"],
        effective_from=now,
    )
    session.add(entitlement)
    return entitlement


def provision_identity(
    session: Session,
    claims: IdentityClaims,
    *,
    requested_organization_id: str | None = None,
) -> TenantContext:
    """Create a user's personal tenant once and resolve an active membership."""
    now = datetime.now(UTC)
    existing_query = (
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            User.issuer == claims.issuer,
            User.subject == claims.subject,
            Membership.status == "active",
            Organization.deleted_at.is_(None),
        )
    )
    if requested_organization_id:
        existing_query = existing_query.where(
            Membership.organization_id == requested_organization_id
        )
    else:
        existing_query = existing_query.where(Organization.personal_owner_user_id == User.id)
    existing = session.execute(existing_query).one_or_none()
    if existing is not None:
        user, membership = existing
        if user.status != "active":
            raise AuthenticationRejected("user is disabled")
        if user.last_login_at <= now - timedelta(minutes=5):
            user.last_login_at = now
        if claims.email and user.email != claims.email:
            user.email = claims.email
            user.email_normalized = _normalized_email(claims.email)
        if claims.display_name.strip() and user.display_name != claims.display_name.strip():
            user.display_name = claims.display_name.strip()
        return TenantContext(
            user_id=user.id,
            organization_id=membership.organization_id,
            membership_id=membership.id,
            role=membership.role,
            issuer=user.issuer,
            subject=user.subject,
        )

    user = session.scalar(
        select(User).where(User.issuer == claims.issuer, User.subject == claims.subject)
    )
    if user is None:
        _advisory_lock(session, f"identity:{claims.issuer}:{claims.subject}")
        user = session.scalar(
            select(User).where(User.issuer == claims.issuer, User.subject == claims.subject)
        )
    if user is None:
        user = User(
            id=(
                DEFAULT_LOCAL_USER_ID
                if claims.issuer == LOCAL_ISSUER and claims.subject == DEFAULT_LOCAL_SUBJECT
                else new_ulid()
            ),
            issuer=claims.issuer,
            subject=claims.subject,
            email=claims.email,
            email_normalized=_normalized_email(claims.email),
            display_name=claims.display_name.strip() or "Instant PPT user",
            status="active",
            last_login_at=now,
        )
        session.add(user)
        session.flush()
        organization = None
        if user.id == DEFAULT_LOCAL_USER_ID:
            organization = session.get(Organization, SYNTHETIC_ORGANIZATION_ID)
        if organization is None:
            organization = Organization(
                id=new_ulid(),
                kind="personal",
                name=_personal_name(claims),
                slug=f"personal-{user.id.lower()}",
                personal_owner_user_id=user.id,
                lock_version=1,
            )
            session.add(organization)
            session.flush()
        else:
            organization.kind = "personal"
            organization.name = _personal_name(claims)
            organization.slug = f"personal-{user.id.lower()}"
            organization.personal_owner_user_id = user.id
            organization.lock_version += 1
        membership = Membership(
            id=new_ulid(),
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
        session.add(membership)
        _add_default_entitlement(session, organization.id, now)
        session.flush()
    else:
        if user.status != "active":
            raise AuthenticationRejected("user is disabled")
        if user.last_login_at <= now - timedelta(minutes=5):
            user.last_login_at = now
        if claims.email and user.email != claims.email:
            user.email = claims.email
            user.email_normalized = _normalized_email(claims.email)
        if claims.display_name.strip() and user.display_name != claims.display_name.strip():
            user.display_name = claims.display_name.strip()

    membership_query = (
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.status == "active",
            Organization.deleted_at.is_(None),
        )
    )
    if requested_organization_id:
        membership_query = membership_query.where(
            Membership.organization_id == requested_organization_id
        )
    else:
        membership_query = membership_query.where(Organization.personal_owner_user_id == user.id)
    membership = session.scalar(membership_query)
    if membership is None:
        raise TenantNotFound("organization does not exist or is not accessible")
    return TenantContext(
        user_id=user.id,
        organization_id=membership.organization_id,
        membership_id=membership.id,
        role=membership.role,
        issuer=user.issuer,
        subject=user.subject,
    )


_SENSITIVE_DETAIL_PARTS = (
    "authorization",
    "token",
    "secret",
    "password",
    "url",
    "prompt",
    "content",
    "body",
)


def sanitize_audit_details(details: dict[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (details or {}).items():
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_DETAIL_PARTS):
            continue
        if isinstance(value, str):
            sanitized[key] = value[:240]
        elif isinstance(value, (bool, int, float)) or value is None:
            sanitized[key] = value
    return sanitized


def append_audit(
    session: Session,
    context: TenantContext,
    *,
    resource_type: str,
    resource_id: str,
    action: str,
    request_id: str,
    outcome: str,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        id=new_ulid(),
        organization_id=context.organization_id,
        actor_id=context.user_id,
        actor_kind="user",
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        request_id=request_id,
        outcome=outcome,
        details=sanitize_audit_details(details),
    )
    session.add(row)
    return row


def entitlement_snapshot(session: Session, organization_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    row = session.scalar(
        select(Entitlement).where(
            Entitlement.organization_id == organization_id,
            Entitlement.effective_from <= now,
            (Entitlement.effective_until.is_(None) | (Entitlement.effective_until > now)),
        )
    )
    if row is None:
        raise TenantNotFound("entitlement is not configured")
    return {
        "planCode": row.plan_code,
        "maxSlidesPerDeck": row.max_slides_per_deck,
        "monthlySlideLimit": row.monthly_slide_limit,
        "maxImagesPerDeck": row.max_images_per_deck,
        "monthlyImageLimit": row.monthly_image_limit,
        "monthlyImageCostLimitMicrounits": row.monthly_image_cost_limit_microunits,
        "maxConcurrentJobs": row.max_concurrent_jobs,
        "allowedModes": list(row.allowed_modes),
        "effectiveFrom": row.effective_from.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "effectiveUntil": (
            row.effective_until.astimezone(UTC).isoformat().replace("+00:00", "Z")
            if row.effective_until
            else None
        ),
    }


def usage_snapshot(session: Session, organization_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    period_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    totals = dict(
        session.execute(
            select(UsageLedger.metric, func.coalesce(func.sum(UsageLedger.quantity), 0))
            .where(
                UsageLedger.organization_id == organization_id,
                UsageLedger.occurred_at >= period_start,
            )
            .group_by(UsageLedger.metric)
        ).all()
    )
    reserved = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_units), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    reserved_images = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_images), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    reserved_image_cost = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_cost_microunits), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    return {
        "periodStart": period_start.isoformat().replace("+00:00", "Z"),
        "asOf": now.isoformat().replace("+00:00", "Z"),
        "metrics": {
            "slides": int(totals.get("slides", 0)),
            "modelTokens": int(totals.get("model_tokens", 0)),
            "images": int(totals.get("images", 0)),
            "imageCostMicrounits": int(totals.get("image_cost_microunits", 0)),
            "workerSeconds": int(totals.get("worker_seconds", 0)),
            "exports": int(totals.get("exports", 0)),
        },
        "reservedSlides": int(reserved or 0),
        "reservedImages": int(reserved_images or 0),
        "reservedImageCostMicrounits": int(reserved_image_cost or 0),
    }

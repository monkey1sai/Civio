"""PostgreSQL enum types mirrored as Python ``str`` enums.

Every enum here corresponds 1:1 to a ``CREATE TYPE`` in
``docs/02-database-schema.sql``. Each Python enum is paired with a shared
``ENUM`` instance (``*_type``) so every model binds to the *same* type object
— that way Alembic autogenerate emits one ``CREATE TYPE`` per enum regardless
of how many tables use it.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM


class CommunityStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class OwnershipStatus(str, Enum):
    OWNED = "owned"
    SOLD = "sold"
    PENDING_TRANSFER = "pending_transfer"
    RENTED = "rented"


class OccupancyStatus(str, Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    RENTED = "rented"


class UserRole(str, Enum):
    OWNER = "owner"
    TENANT = "tenant"
    FAMILY = "family"
    ADMIN = "admin"
    STAFF = "staff"


class AuthStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REVOKED = "revoked"


class RelationType(str, Enum):
    RESIDENT = "resident"
    FAMILY = "family"
    TENANT = "tenant"


class FriendStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    REMOVED = "removed"


class TokenScope(str, Enum):
    COMMUNITY = "community"
    USER = "user"


class CallStatus(str, Enum):
    INIT = "init"
    RINGING = "ringing"
    ANSWERED = "answered"
    ENDED = "ended"
    REJECTED = "rejected"
    FAILED = "failed"


class BillingScope(str, Enum):
    USER = "user"
    COMMUNITY = "community"
    FREE = "free"


class SyncAckStatus(str, Enum):
    PENDING = "pending"
    ACKED = "acked"
    FAILED = "failed"


class AnnouncementPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ---------------------------------------------------------------------------
# Shared ``ENUM`` singletons. Every model column that stores one of these enum
# values MUST import the ``*_type`` from here, not construct a new ``ENUM(...)``
# inline — that way Alembic autogenerate emits a single ``CREATE TYPE``.
#
# ``values_callable=_values`` forces SQLAlchemy to use each member's ``.value``
# (lowercase, e.g. ``"pending"``) rather than its ``.name`` (``"PENDING"``).
# The DDL declares the type as ``ENUM('pending', ...)`` — without this kwarg,
# Alembic autogenerate would emit the uppercase names and every ``server_default``
# would reference a value that doesn't exist in the enum.
# ---------------------------------------------------------------------------
def _values(enum_cls: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


community_status_type = ENUM(CommunityStatus, name="community_status", values_callable=_values)
ownership_status_type = ENUM(OwnershipStatus, name="ownership_status", values_callable=_values)
occupancy_status_type = ENUM(OccupancyStatus, name="occupancy_status", values_callable=_values)
user_role_type = ENUM(UserRole, name="user_role", values_callable=_values)
auth_status_type = ENUM(AuthStatus, name="auth_status", values_callable=_values)
relation_type_type = ENUM(RelationType, name="relation_type", values_callable=_values)
friend_status_type = ENUM(FriendStatus, name="friend_status", values_callable=_values)
token_scope_type = ENUM(TokenScope, name="token_scope", values_callable=_values)
call_status_type = ENUM(CallStatus, name="call_status", values_callable=_values)
billing_scope_type = ENUM(BillingScope, name="billing_scope", values_callable=_values)
sync_ack_status_type = ENUM(SyncAckStatus, name="sync_ack_status", values_callable=_values)
announcement_priority_type = ENUM(
    AnnouncementPriority, name="announcement_priority", values_callable=_values
)

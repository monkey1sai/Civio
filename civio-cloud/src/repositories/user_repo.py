"""User-specific queries on top of :class:`BaseRepository`."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_mobile(self, community_id: UUID, mobile: str) -> User | None:
        stmt = select(User).where(
            User.community_id == community_id,
            User.mobile == mobile,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_mobile(self, mobile: str) -> Sequence[User]:
        """Every user matching a mobile across communities.

        OTP send is tenant-agnostic — the mobile uniquely identifies a person
        within a community, but the same number may legitimately exist in
        multiple communities (e.g. a property manager serving several). The
        auth service disambiguates at verify time.
        """
        stmt = select(User).where(User.mobile == mobile)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_community(self, community_id: UUID) -> Sequence[User]:
        stmt = select(User).where(User.community_id == community_id).order_by(User.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().all()

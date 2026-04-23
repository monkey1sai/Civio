"""Generic async repository.

``BaseRepository`` provides the five CRUD primitives every entity needs. Each
concrete repository inherits and adds domain-specific queries — routers and
services must go through these classes; raw SQL in the service layer is
forbidden by ``CLAUDE.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD primitives bound to a single ORM model and session."""

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, id: UUID) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        **filters: object,
    ) -> Sequence[ModelT]:
        stmt = select(self.model).offset(skip).limit(limit)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs: object) -> ModelT:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, id: UUID, **kwargs: object) -> ModelT:
        instance = await self.get(id)
        if instance is None:
            raise NotFoundError(
                f"{self.model.__name__} not found",
                details={"id": str(id)},
            )
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def delete(self, id: UUID) -> None:
        # ORM-level delete handles cascades via relationship config; a bulk
        # ``DELETE WHERE id=...`` statement would bypass them.
        instance = await self.get(id)
        if instance is None:
            return
        await self.session.delete(instance)
        await self.session.flush()

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class ActionType(str, enum.Enum):
    VIEW = "VIEW"
    EDIT = "EDIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RECLASSIFY = "RECLASSIFY"
    REGENERATE = "REGENERATE"


class OperatorAction(Base, TimestampMixin):
    __tablename__ = "operator_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[ActionType] = mapped_column(SAEnum(ActionType))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    ticket: Mapped[Ticket] = relationship(back_populates="actions")
    user: Mapped[User | None] = relationship(back_populates="actions")

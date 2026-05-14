"""Importing this package registers all ORM models on Base.metadata."""
from app.models.base import Base, TimestampMixin
from app.models.category import Category
from app.models.classification import Classification
from app.models.draft import Draft
from app.models.kpi_event import KpiEvent, KpiEventType
from app.models.operator_action import ActionType, OperatorAction
from app.models.prompt_template import PromptKind, PromptTemplate
from app.models.reference import Reference
from app.models.ticket import Ticket, TicketStatus
from app.models.upload import Upload
from app.models.user import User, UserRole
from app.models.webhook_inbox import InboxStatus, WebhookInbox

__all__ = [
    "Base",
    "TimestampMixin",
    "Category",
    "Classification",
    "Draft",
    "KpiEvent",
    "KpiEventType",
    "OperatorAction",
    "ActionType",
    "PromptKind",
    "PromptTemplate",
    "Reference",
    "Ticket",
    "TicketStatus",
    "Upload",
    "User",
    "UserRole",
    "WebhookInbox",
    "InboxStatus",
]

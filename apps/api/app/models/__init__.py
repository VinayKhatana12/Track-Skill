"""ORM models package. Import every model here so Alembic sees full metadata."""

from app.models.activity import Event, Notification
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.centre import ProviderStaff, TrainingCentre
from app.models.contact import ContactMessage
from app.models.course import Course
from app.models.employer import Employer
from app.models.employment import EmploymentRecord, Verification
from app.models.followup import FollowUp
from app.models.governance import FundAllocation, ProviderScore
from app.models.market import MarketDemand
from app.models.push import PushSubscription
from app.models.trainee import Consent, Trainee
from app.models.user import User

__all__ = [
    "Base",
    "Consent",
    "ContactMessage",
    "Course",
    "Employer",
    "EmploymentRecord",
    "Event",
    "FollowUp",
    "FundAllocation",
    "MarketDemand",
    "Notification",
    "ProviderScore",
    "ProviderStaff",
    "PushSubscription",
    "TimestampMixin",
    "Trainee",
    "TrainingCentre",
    "UUIDPrimaryKeyMixin",
    "User",
    "Verification",
]

"""Enum types shared across the TrackSkill AI domain models."""

import enum


class UserRole(enum.StrEnum):
    """Department roles, enforced by backend RBAC."""

    PROVIDER = "PROVIDER"
    TRAINEE = "TRAINEE"
    EMPLOYER = "EMPLOYER"
    ADMIN = "ADMIN"


class ConsentChannel(enum.StrEnum):
    """Channels used for consent collection and follow-up tracers."""

    WHATSAPP = "WHATSAPP"
    IVR = "IVR"
    SMS = "SMS"


class TraineeStatus(enum.StrEnum):
    ENROLLED = "ENROLLED"
    CERTIFIED = "CERTIFIED"
    DROPPED = "DROPPED"


class EmploymentStatus(enum.StrEnum):
    EMPLOYED = "EMPLOYED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    UNEMPLOYED = "UNEMPLOYED"
    FURTHER_STUDY = "FURTHER_STUDY"


class FollowUpMilestone(enum.StrEnum):
    """Post-certification tracking milestones."""

    M3 = "M3"
    M6 = "M6"
    M12 = "M12"


class FollowUpState(enum.StrEnum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    RESPONDED = "RESPONDED"
    MISSED = "MISSED"


class VerificationSignal(enum.StrEnum):
    """Dual-signal verification: trainee self-report + employer confirmation."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"

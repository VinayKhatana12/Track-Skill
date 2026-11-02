"""Shared domain constants used by services and the seed."""

from app.models.enums import ConsentChannel, EmploymentStatus, FollowUpMilestone

CONSENT_VERSION = "1.0"
CONSENT_PURPOSE = (
    "Outcome tracking follow-ups at 3, 6 and 12 months after certification. "
    "You can withdraw consent at any time."
)

MILESTONE_OFFSET_DAYS: dict[FollowUpMilestone, int] = {
    FollowUpMilestone.M3: 90,
    FollowUpMilestone.M6: 182,
    FollowUpMilestone.M12: 365,
}

WORKING_STATUSES = {EmploymentStatus.EMPLOYED, EmploymentStatus.SELF_EMPLOYED}

# Channels a trainee can grant consent for (ordering matters for defaults).
CONSENT_CHANNELS = (ConsentChannel.WHATSAPP, ConsentChannel.IVR, ConsentChannel.SMS)

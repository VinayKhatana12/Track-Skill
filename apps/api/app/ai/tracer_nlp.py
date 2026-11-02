"""Tracer message generator and free-text reply parser.

Templates are English-only (product rule) and channel-specific — the
simulated WhatsApp / IVR / SMS delivery layer renders these instead of
sending real messages.

The reply parser turns free-text answers (typed WhatsApp replies or IVR
voice transcripts) into structured ``response_json``:

- employment status via keyword families (worked examples in the tests),
- monthly wage via "N per month" / "earning N" style patterns,
- job title via "as a <title>" / "working as a <title>" capture,
- employer via company-name lookup done by the caller (the parser is
  database-free and pure).

Every parse carries a confidence in 0..1; below
MANUAL_REVIEW_THRESHOLD the response is flagged ``needs_review`` so a
provider staff member confirms it manually. The rules are deliberately
simple and explainable — they run in the light-NLP mode on any laptop.
"""

import logging
import re

logger = logging.getLogger(__name__)

MANUAL_REVIEW_THRESHOLD = 0.6

MILESTONE_MONTHS = {"M3": 3, "M6": 6, "M12": 12}

# Employment keyword families, checked in priority order. The families are
# intentionally disjoint so a single reply maps to exactly one status.
_EMPLOYED_PATTERNS = (
    r"\bgot (?:a|my) job\b",
    r"\bhired\b",
    r"\bworking\b",
    r"\bjoined\b",
    r"\bstarted work\b",
    r"\bemployed\b",
    r"\bin a job\b",
)
_SELF_EMPLOYED_PATTERNS = (
    r"\bself[- ]?employ",
    r"\bown (?:business|shop|work|venture)\b",
    r"\bfreelanc",
)
_UNEMPLOYED_PATTERNS = (
    r"\bunemploy",
    r"\bno job\b",
    r"\blost (?:my|the) job\b",
    r"\bstill (?:looking|searching)\b",
    r"\bnot working\b",
)
_FURTHER_STUDY_PATTERNS = (
    r"\bstudying\b",
    r"\benrolled in\b",
    r"\bhigher stud",
    r"\bcollege\b",
    r"\buniversity\b",
    r"\bdiploma\b",
)

_WAGE_PATTERNS = (
    r"(\d[\d,]{3,7})\s*(?:per month|monthly|/month|a month|pm\b|salary)",
    r"(?:salary|wage|earning[s]?|pay)\s*(?:of|is|:)?\s*(\d[\d,]{3,7})",
)
_TITLE_PATTERN = re.compile(
    r"(?:job|work(?:ing)?|hired|employ(?:ed)?)\s+(?:as\s+)?(?:an?\s+|my\s+)?"
    r"(?P<title>[a-z][a-z ]{2,40}?)(?=,|\.|!|\bat\b|\band\b|\bearning\b|\bfor\b|\bper\b"
    r"|\blast\b|\bthis\b|\btoday\b|\byesterday\b|$)",
    re.IGNORECASE,
)

EMPLOYED = "EMPLOYED"
SELF_EMPLOYED = "SELF_EMPLOYED"
UNEMPLOYED = "UNEMPLOYED"
FURTHER_STUDY = "FURTHER_STUDY"


def build_followup_message(
    *,
    channel: str,
    trainee_name: str,
    course_title: str,
    milestone: str,
    centre_name: str,
) -> str:
    """Render the outbound tracer message for a channel (English-only)."""
    months = MILESTONE_MONTHS.get(milestone, 3)
    first_name = trainee_name.split(" ")[0]
    if channel == "IVR":
        return (
            f"Hello {first_name}, this is an automated call from {centre_name}. "
            f"It has been {months} months since your {course_title} certification. "
            "Press 1 if you are employed, Press 2 if you are self-employed, "
            "Press 3 if you are unemployed, Press 4 if you are studying further."
        )
    if channel == "SMS":
        return (
            f"TrackSkill AI: {first_name}, your {milestone} follow-up "
            f"({months} months after {course_title}) is due. Reply with your "
            "current employment status and monthly salary if working."
        )
    # Default: WhatsApp style with a worked example (helps the parser too).
    return (
        f"Hi {first_name}! It has been {months} months since you completed "
        f"{course_title} at {centre_name}. Are you working currently? If yes, "
        "reply with your role and monthly salary, for example: "
        "'I got a job as a welder, 14000 per month'. If you are "
        "self-employed, studying or looking for work, just tell us."
    )


class ParsedReply:
    """Structured result of parsing one free-text tracer reply."""

    def __init__(
        self,
        employment_status: str | None,
        job_title: str | None,
        monthly_wage: int | None,
        confidence: float,
    ) -> None:
        self.employment_status = employment_status
        self.job_title = job_title
        self.monthly_wage = monthly_wage
        self.confidence = round(max(0.0, min(confidence, 1.0)), 2)
        self.needs_review = (
            employment_status is None or confidence < MANUAL_REVIEW_THRESHOLD
        )

    def to_dict(self) -> dict:
        return {
            "employment": self.employment_status,
            "job_title": self.job_title,
            "wage": self.monthly_wage,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
        }


def _detect_employment(text: str) -> str | None:
    for status_value, patterns in (
        (FURTHER_STUDY, _FURTHER_STUDY_PATTERNS),
        (SELF_EMPLOYED, _SELF_EMPLOYED_PATTERNS),
        (UNEMPLOYED, _UNEMPLOYED_PATTERNS),
        (EMPLOYED, _EMPLOYED_PATTERNS),
    ):
        if any(re.search(pattern, text) for pattern in patterns):
            return status_value
    return None


def _detect_wage(text: str) -> int | None:
    for pattern in _WAGE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _detect_title(text: str) -> str | None:
    match = _TITLE_PATTERN.search(text)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group("title")).strip(" .,-")
    if len(title) < 3:
        return None
    return title.title()


def parse_reply(text: str) -> ParsedReply:
    """Parse one free-text tracer reply into structured fields + confidence."""
    normalised = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalised:
        return ParsedReply(None, None, None, 0.0)

    employment_status = _detect_employment(normalised)
    working = employment_status in (EMPLOYED, SELF_EMPLOYED)
    job_title = _detect_title(normalised) if working else None
    monthly_wage = _detect_wage(normalised)

    if employment_status is None:
        confidence = 0.15
    else:
        confidence = 0.35 + 0.30
        if monthly_wage is not None:
            confidence += 0.15
        elif employment_status not in (EMPLOYED, SELF_EMPLOYED):
            confidence += 0.10  # a clear "not working" needs no wage
        if job_title:
            confidence += 0.15

    logger.info(
        "Parsed tracer reply: status=%s title=%s wage=%s confidence=%.2f",
        employment_status,
        job_title,
        monthly_wage,
        confidence,
    )
    return ParsedReply(employment_status, job_title, monthly_wage, confidence)

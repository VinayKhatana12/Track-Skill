"""Skill assessment: evidence in, skill profile + job-role matches out.

Inputs (Objective 2):
- the trainee's course skills (from the DB),
- self-described skills (free-form strings),
- optional free text / voice-transcript answers.

Approach: every piece of evidence is embedded (sentence-transformers or the
hashed fallback), every taxonomy skill is embedded once per process, and a
skill's confidence is the best cosine similarity across the evidence —
boosted to ~0.95 when the skill name or an alias appears verbatim, which
makes exact self-reports deterministic in both modes. Confidence is clipped
to 0..1 and the profile is thresholded so weak similarities are dropped.

Job-role matching is deliberately rule-based on top of the profile: each
role is a weighted skill set, and the score is the weight-average of the
matched confidences. This keeps explanations fully traceable ("matched on
Skill X at 0.91"), which matters more for governance than opaque scores.
"""

import logging
from functools import lru_cache

from app.ai import taxonomy
from app.ai.embedder import cosine, get_embedder

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _taxonomy_vectors() -> dict[str, list[float]]:
    """Embed each taxonomy skill once per process (name + aliases averaged)."""
    embedder = get_embedder()
    names = [skill[0] for skill in taxonomy.SKILLS]
    vectors = embedder.encode(names)
    return dict(zip(names, vectors, strict=True))


@lru_cache(maxsize=1)
def _mode_label() -> str:
    embedder_name = get_embedder().__class__.__name__
    mode = "light-nlp" if embedder_name == "HashingEmbedder" else "sentence-transformers"
    return mode


def _normalise_confidence(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 2)


def assess_skills(
    *,
    course_skills: list[str],
    self_reported_skills: list[str] | None = None,
    free_text: str | None = None,
) -> dict:
    """Build a skill profile and the top-5 job-role matches."""
    evidence: list[str] = []
    evidence.extend(skill.strip() for skill in (self_reported_skills or []) if skill.strip())
    if course_skills:
        evidence.extend(course_skills)
    if free_text and free_text.strip():
        evidence.append(free_text.strip())

    if not evidence:
        return {
            "profile": [],
            "role_matches": [],
            "mode": _mode_label(),
            "evidence_count": 0,
        }

    embedder = get_embedder()
    evidence_vectors = embedder.encode(evidence)
    evidence_blob = " \n".join(evidence).lower()

    profile: list[dict] = []
    for skill_name, skill_vector in _taxonomy_vectors().items():
        sector, aliases = taxonomy.SKILL_BY_NAME[skill_name]

        # Verbatim mention (canonical name or alias) is near-certain evidence.
        mentioned = skill_name.lower() in evidence_blob or any(
            alias.lower() in evidence_blob for alias in aliases
        )
        confidence = max(
            (cosine(skill_vector, evidence_vector) for evidence_vector in evidence_vectors),
            default=0.0,
        )
        if mentioned:
            confidence = max(confidence, taxonomy.EXACT_MATCH_CONFIDENCE)
        confidence = _normalise_confidence(confidence)
        if confidence >= taxonomy.PROFILE_CONFIDENCE_THRESHOLD:
            profile.append(
                {"skill": skill_name, "sector": sector, "confidence": confidence}
            )

    profile.sort(key=lambda item: (-item["confidence"], item["skill"]))

    role_matches = _match_roles(profile)
    logger.info(
        "Skill assessment produced %s skill(s) and %s role match(es) [mode=%s]",
        len(profile),
        len(role_matches),
        _mode_label(),
    )
    return {
        "profile": profile[:15],
        "role_matches": role_matches[:5],
        "mode": _mode_label(),
        "evidence_count": len(evidence),
    }


def _match_roles(profile: list[dict]) -> list[dict]:
    """Weight-average of matched confidences per role, with explanations."""
    confidence_by_skill = {item["skill"]: item["confidence"] for item in profile}
    matches = []
    for role in taxonomy.JOB_ROLES:
        matched: list[tuple[str, float, float]] = []
        weight_total = 0.0
        score_total = 0.0
        for skill_name, weight in role["skills"].items():
            weight_total += weight
            confidence = confidence_by_skill.get(skill_name)
            if confidence is not None:
                matched.append((skill_name, weight, confidence))
                score_total += weight * confidence
        if not matched:
            continue
        score = score_total / weight_total if weight_total else 0.0
        matched.sort(key=lambda item: -item[2])
        explanation = "Matches on: " + ", ".join(
            f"{skill_name} ({confidence:.2f})" for skill_name, _, confidence in matched
        )
        matches.append(
            {
                "title": role["title"],
                "sector": role["sector"],
                "score": round(score, 3),
                "matched_skills": [
                    {"skill": skill_name, "confidence": confidence}
                    for skill_name, _, confidence in matched
                ],
                "explanation": explanation,
            }
        )
    matches.sort(key=lambda item: (-item["score"], item["title"]))
    return matches

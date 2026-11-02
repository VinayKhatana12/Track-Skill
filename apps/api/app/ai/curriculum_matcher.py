"""Curriculum-to-demand matcher (Objective 2, per-course view).

For every course, compares the skills it teaches against the in-demand
skills for its district and sector (latest ``market_demand`` month) and
reports:

- coverage: demand-weighted share of in-demand skills the course teaches,
- gap_score: 1 - coverage,
- missing_in_demand_skills: the highest-demand skills it does not teach,
- suggested_modules: concrete module additions for the top missing skills.

Matching is lexical by design (token overlap plus taxonomy aliases) so the
report stays explainable to non-technical reviewers. Reports are computed
fresh per call — market demand changes monthly, so nothing is cached.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import taxonomy
from app.models import Course, MarketDemand, TrainingCentre

logger = logging.getLogger(__name__)

_MISSING_SKILL_LIMIT = 6
_SUGGESTED_MODULE_LIMIT = 3
_COVERAGE_PER_COURSE = 3.0  # a course covering >= 3 in-demand skills is "covered"


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens with plural stripping (tiny, explainable)."""
    tokens = set()
    for word in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split():
        if len(word) > 1:
            tokens.add(word[:-1] if word.endswith("s") and len(word) > 3 else word)
    return tokens


def _latest_demand(db: Session) -> dict[tuple[str, str], float]:
    """(district, skill) -> demand score for the most recent month."""
    months = db.execute(select(MarketDemand.month).distinct()).scalars().all()
    if not months:
        return {}
    latest = max(months)
    return {
        (row.district, row.skill): row.demand_score
        for row in db.execute(select(MarketDemand).where(MarketDemand.month == latest)).scalars()
    }


def _taxonomy_index() -> dict[str, set[str]]:
    """Taxonomy skill -> token set (canonical name plus aliases)."""
    index: dict[str, set[str]] = {}
    for name, _, aliases in taxonomy.SKILLS:
        tokens = _tokenize(name)
        for alias in aliases:
            tokens |= _tokenize(alias)
        index[name] = tokens
    return index


def _sector_of_skill(skill: str, index: dict[str, set[str]]) -> str | None:
    """Resolve a demand skill to its taxonomy sector via tokens/aliases."""
    if skill in taxonomy.SKILL_SECTOR:
        return taxonomy.SKILL_SECTOR[skill]
    skill_tokens = _tokenize(skill)
    best_name, best_overlap = None, 0
    for name, tokens in index.items():
        overlap = len(skill_tokens & tokens)
        if overlap > best_overlap:
            best_name, best_overlap = name, overlap
    return taxonomy.SKILL_SECTOR.get(best_name) if best_name else None


def _covers(course_tokens: set[str], skill: str, index: dict[str, set[str]]) -> bool:
    """True when the course touches the demand skill directly or through a
    taxonomy skill whose tokens overlap both."""
    demand_tokens = _tokenize(skill)
    if demand_tokens & course_tokens:
        return True
    for taxonomy_tokens in index.values():
        if (demand_tokens & taxonomy_tokens) and (taxonomy_tokens & course_tokens):
            return True
    return False


def course_gap_report(db: Session, limit: int = 50) -> list[dict]:
    """Per-course curriculum-demand gap report, worst gaps first."""
    demand = _latest_demand(db)
    if not demand:
        return []
    index = _taxonomy_index()

    courses = db.execute(
        select(Course, TrainingCentre)
        .join(TrainingCentre, Course.centre_id == TrainingCentre.id)
        .order_by(TrainingCentre.name, Course.title)
    ).all()

    report: list[dict] = []
    for course, centre in courses:
        in_demand = {
            skill: score
            for (district, skill), score in demand.items()
            if district == centre.district and _sector_of_skill(skill, index) == course.sector
        }
        if not in_demand:
            continue

        course_tokens: set[str] = set()
        for skill in course.skills or []:
            course_tokens |= _tokenize(skill)

        covered_weight = 0.0
        missing: list[dict] = []
        total_weight = 0.0
        covered_count = 0
        for skill, score in sorted(in_demand.items(), key=lambda item: -item[1]):
            total_weight += score
            if _covers(course_tokens, skill, index):
                covered_weight += score
                covered_count += 1
            else:
                missing.append({"skill": skill, "demand_score": round(score, 1)})

        coverage = covered_weight / total_weight if total_weight else 0.0
        suggested_modules = [
            f"Add a module on '{item['skill']}' (district demand {item['demand_score']:.0f}/100)"
            for item in missing[:_SUGGESTED_MODULE_LIMIT]
        ]
        report.append(
            {
                "course_id": str(course.id),
                "title": course.title,
                "sector": course.sector,
                "centre_name": centre.name,
                "district": centre.district,
                "course_skills": list(course.skills or []),
                "covered_in_demand": covered_count,
                "coverage": round(coverage, 3),
                "gap_score": round(1.0 - coverage, 3),
                "missing_in_demand_skills": missing[:_MISSING_SKILL_LIMIT],
                "suggested_modules": suggested_modules,
                "_covered_weight": covered_weight,
                "_course_count_in_demand": covered_count >= _COVERAGE_PER_COURSE,
            }
        )
        if len(report) >= limit:
            break

    report.sort(key=lambda item: (-item["gap_score"], item["title"]))
    for item in report:
        item.pop("_covered_weight", None)
        item.pop("_course_count_in_demand", None)
    return report

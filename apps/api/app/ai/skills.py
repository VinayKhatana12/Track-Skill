"""Lightweight TF-IDF skill matching — the AI module's fallback mode.

sentence-transformers arrives in the AI phase; this deterministic TF-IDF path
already powers ``GET /trainee/skills`` (recommended skills + courses) and
``GET /admin/curriculum-gaps`` (demand vs. course coverage). Everything is
computed from ``market_demand`` and ``courses``, so results are explainable.
"""

import math
import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, MarketDemand, TrainingCentre

_SUFFIXES = ("ing", "ion", "ment", "ness", "ers", "es", "s")


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens with light suffix stripping."""
    tokens = set()
    for raw in re.findall(r"[a-zA-Z]+", text.lower()):
        token = raw
        for suffix in _SUFFIXES:
            if len(token) > 4 and token.endswith(suffix):
                token = token[: -len(suffix)]
                break
        tokens.add(token)
    return tokens


def _tfidf_matrix(corpus: list[str]) -> list[dict[str, float]]:
    token_sets = [_tokenize(document) for document in corpus]
    document_frequency: dict[str, int] = defaultdict(int)
    for tokens in token_sets:
        for token in tokens:
            document_frequency[token] += 1
    total = max(1, len(corpus))
    idf = {token: math.log(total / count) + 1.0 for token, count in document_frequency.items()}
    matrix = []
    for tokens in token_sets:
        weights = {token: (1.0 / len(tokens)) * idf[token] for token in tokens} if tokens else {}
        norm = math.sqrt(sum(weight * weight for weight in weights.values())) or 1.0
        matrix.append({token: weight / norm for token, weight in weights.items()})
    return matrix


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    small, large = (left, right) if len(left) <= len(right) else (right, left)
    return sum(weight * large.get(token, 0.0) for token, weight in small.items())


def _demand_by_skill(db: Session, district: str | None = None) -> dict[str, dict]:
    """Average demand per skill over the most recent month of market data."""
    months = db.execute(select(MarketDemand.month).distinct()).scalars().all()
    if not months:
        return {}
    latest = max(months)
    statement = select(MarketDemand).where(MarketDemand.month == latest)
    if district:
        statement = statement.where(MarketDemand.district == district)
    aggregated: dict[str, dict] = {}
    for row in db.execute(statement).scalars():
        entry = aggregated.setdefault(row.skill, {"sector": row.sector, "scores": []})
        entry["scores"].append(row.demand_score)
    return {
        skill: {"sector": data["sector"], "demand": sum(data["scores"]) / len(data["scores"])}
        for skill, data in aggregated.items()
    }


def _course_rows(db: Session) -> list[dict]:
    rows = []
    for course, centre in db.execute(
        select(Course, TrainingCentre).join(TrainingCentre, Course.centre_id == TrainingCentre.id)
    ).all():
        rows.append(
            {
                "id": str(course.id),
                "title": course.title,
                "sector": course.sector,
                "centre_name": centre.name,
                "skills": course.skills or [],
            }
        )
    return rows


def _courses_for_skill(rows: list[dict], skill: str, limit: int = 3) -> list[dict]:
    skill_tokens = _tokenize(skill)
    matches = []
    for row in rows:
        course_tokens = (
            set().union(*(_tokenize(s) for s in row["skills"])) if row["skills"] else set()
        )
        overlap = len(skill_tokens & course_tokens)
        if skill.lower() in (s.lower() for s in row["skills"]) or overlap:
            matches.append((overlap, row))
    matches.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [
        {"id": row["id"], "title": row["title"], "centre_name": row["centre_name"]}
        for _, row in matches[:limit]
    ]


def recommended_skills(
    db: Session, trainee_skills: list[str], district: str | None = None, limit: int = 5
) -> list[dict]:
    """Skills the trainee does not have yet, ranked by demand and affinity."""
    demands = _demand_by_skill(db, district)
    if not demands:
        return []
    profile_tokens: set[str] = set()
    for skill in trainee_skills:
        profile_tokens |= _tokenize(skill)

    corpus = list(demands.keys())
    matrix = _tfidf_matrix(corpus)

    recommendations = []
    for index, skill in enumerate(corpus):
        info = demands[skill]
        skill_tokens = _tokenize(skill)
        if skill_tokens and skill_tokens <= profile_tokens:
            continue  # already possessed
        similarity = _cosine(matrix[index], dict.fromkeys(profile_tokens, 1.0))
        score = 0.65 * (info["demand"] / 100.0) + 0.35 * similarity
        recommendations.append(
            {
                "skill": skill,
                "sector": info["sector"],
                "demand_score": round(info["demand"], 1),
                "similarity": round(similarity, 3),
                "score": round(score, 3),
            }
        )
    recommendations.sort(key=lambda item: (-item["score"], item["skill"]))

    course_rows = _course_rows(db)
    results = []
    for item in recommendations[:limit]:
        item["courses"] = _courses_for_skill(course_rows, item["skill"])
        results.append(item)
    return results


def curriculum_gaps(db: Session, limit: int = 10) -> list[dict]:
    """Skills with strong market demand but thin course coverage."""
    demands = _demand_by_skill(db)
    if not demands:
        return []
    course_rows = _course_rows(db)
    gaps = []
    for skill, info in demands.items():
        course_count = len(_courses_for_skill(course_rows, skill, limit=100))
        demand_norm = info["demand"] / 100.0
        coverage = min(1.0, course_count / 3.0)
        gaps.append(
            {
                "skill": skill,
                "sector": info["sector"],
                "demand_score": round(info["demand"], 1),
                "course_count": course_count,
                "gap_score": round(demand_norm - 0.5 * coverage, 3),
            }
        )
    gaps.sort(key=lambda item: (-item["gap_score"], item["skill"]))
    return gaps[:limit]

"""Role-aware global search for the top bar."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Course, Trainee, TrainingCentre, User
from app.models.enums import UserRole

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", summary="Search within your role's scope")
def search(
    q: str = Query(min_length=1, max_length=80),
    db: Session = Depends(get_db),
    current_user=Depends(require_role()),
) -> dict:
    needle = f"%{q.strip().lower()}%"
    results: list[dict] = []

    if current_user.role in (UserRole.ADMIN, UserRole.PROVIDER):
        trainees = db.execute(
            select(Trainee, User)
            .join(User, Trainee.user_id == User.id)
            .where(or_(User.name.ilike(needle), User.email.ilike(needle)))
            .limit(5)
        ).all()
        for _, user in trainees:
            results.append(
                {"type": "trainee", "label": user.name, "detail": user.email}
            )
    if current_user.role is UserRole.ADMIN:
        centres = db.execute(
            select(TrainingCentre).where(
                or_(TrainingCentre.name.ilike(needle), TrainingCentre.district.ilike(needle))
            ).limit(5)
        ).scalars().all()
        for centre in centres:
            results.append(
                {"type": "centre", "label": centre.name, "detail": centre.district}
            )
    if current_user.role is UserRole.EMPLOYER:
        courses = db.execute(
            select(Course).where(Course.title.ilike(needle)).limit(5)
        ).scalars().all()
        for course in courses:
            results.append({"type": "skill", "label": course.title, "detail": course.sector})
    if current_user.role is UserRole.TRAINEE:
        courses = db.execute(
            select(Course).where(Course.title.ilike(needle)).limit(5)
        ).scalars().all()
        for course in courses:
            results.append({"type": "course", "label": course.title, "detail": course.sector})

    return {"results": results[:10]}

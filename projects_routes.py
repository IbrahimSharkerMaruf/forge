from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import get_current_user, get_current_user_optional
from db import get_db
from models import Application, Message, Project, User
from schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    MessageCreate,
    MessageOut,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    ProjectUpdate,
    ThreadSummary,
)

router = APIRouter()


def serialize_project(db: Session, project: Project) -> dict:
    applicant_count = db.query(Application).filter(Application.project_id == project.id).count()
    return {
        "id": project.id,
        "owner": project.owner,
        "title": project.title,
        "description": project.description,
        "skills": [s.strip() for s in project.skills.split(",") if s.strip()],
        "status": project.status,
        "created_at": project.created_at,
        "applicant_count": applicant_count,
    }


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects", response_model=ProjectOut)
def create_project(
    req: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    project = Project(
        owner_id=user.id,
        title=req.title,
        description=req.description,
        skills=", ".join(s.strip() for s in req.skills if s.strip()),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    status: str | None = None,
    mine: bool = False,
    applied: bool = False,
    collaborating: bool = False,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    if mine:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        query = query.filter(Project.owner_id == user.id)
    if applied:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        applied_ids = [
            a.project_id
            for a in db.query(Application).filter(Application.applicant_id == user.id).all()
        ]
        query = query.filter(Project.id.in_(applied_ids or [-1]))
    if collaborating:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        accepted_ids = [
            a.project_id
            for a in db.query(Application).filter(
                Application.applicant_id == user.id, Application.status == "accepted"
            ).all()
        ]
        query = query.filter(Project.id.in_(accepted_ids or [-1]))

    projects = query.order_by(Project.created_at.desc()).all()
    return [serialize_project(db, p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    data = serialize_project(db, project)

    credited = []
    if project.status == "completed":
        credited.append(project.owner)
        accepted = (
            db.query(Application)
            .filter(Application.project_id == project.id, Application.status == "accepted")
            .all()
        )
        credited.extend(a.applicant for a in accepted)
    data["credited"] = credited

    data["my_application"] = None
    data["applications"] = None
    if user:
        if user.id == project.owner_id:
            apps = db.query(Application).filter(Application.project_id == project.id).all()
            data["applications"] = apps
        else:
            my_app = (
                db.query(Application)
                .filter(Application.project_id == project.id, Application.applicant_id == user.id)
                .first()
            )
            data["my_application"] = my_app

    return data


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    req: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")

    if req.title is not None:
        project.title = req.title
    if req.description is not None:
        project.description = req.description
    if req.skills is not None:
        project.skills = ", ".join(s.strip() for s in req.skills if s.strip())
    if req.status is not None:
        if req.status not in ("open", "completed"):
            raise HTTPException(status_code=400, detail="Status must be 'open' or 'completed'")
        project.status = req.status

    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    project = get_project_or_404(db, project_id)
    if project.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the project owner can do this")
    db.query(Application).filter(Application.project_id == project_id).delete()
    db.query(Message).filter(Message.project_id == project_id).delete()
    db.delete(project)
    db.commit()


@router.post("/projects/{project_id}/apply", response_model=ApplicationOut)
def apply_to_project(
    project_id: int,
    req: ApplicationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    if project.owner_id == user.id:
        raise HTTPException(status_code=400, detail="You can't apply to your own project")
    if project.status != "open":
        raise HTTPException(status_code=400, detail="This project isn't accepting applicants")

    existing = (
        db.query(Application)
        .filter(Application.project_id == project_id, Application.applicant_id == user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You already applied to this project")

    application = Application(project_id=project_id, applicant_id=user.id, message=req.message)
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.patch("/projects/{project_id}/applications/{application_id}", response_model=ApplicationOut)
def update_application(
    project_id: int,
    application_id: int,
    req: ApplicationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")
    if req.status not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'accepted' or 'rejected'")

    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.project_id == project_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    application.status = req.status
    db.commit()
    db.refresh(application)
    return application


def assert_can_message(db: Session, project: Project, user: User, counterpart_id: int) -> None:
    if user.id == counterpart_id:
        raise HTTPException(status_code=400, detail="Can't message yourself")
    if user.id == project.owner_id:
        has_application = (
            db.query(Application)
            .filter(Application.project_id == project.id, Application.applicant_id == counterpart_id)
            .first()
        )
        if not has_application:
            raise HTTPException(status_code=403, detail="That person hasn't applied to this project")
    elif counterpart_id != project.owner_id:
        raise HTTPException(status_code=403, detail="You can only message the project owner")


@router.get("/projects/{project_id}/messages", response_model=list[MessageOut])
def get_messages(
    project_id: int,
    with_: int | None = Query(default=None, alias="with"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    counterpart_id = with_ if with_ is not None else project.owner_id
    assert_can_message(db, project, user, counterpart_id)

    messages = (
        db.query(Message)
        .filter(
            Message.project_id == project_id,
            or_(
                (Message.sender_id == user.id) & (Message.recipient_id == counterpart_id),
                (Message.sender_id == counterpart_id) & (Message.recipient_id == user.id),
            ),
        )
        .order_by(Message.created_at.asc())
        .all()
    )
    return messages


@router.post("/projects/{project_id}/messages", response_model=MessageOut)
def send_message(
    project_id: int,
    req: MessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    assert_can_message(db, project, user, req.recipient_id)

    message = Message(
        project_id=project_id,
        sender_id=user.id,
        recipient_id=req.recipient_id,
        body=req.body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/projects/{project_id}/threads", response_model=list[ThreadSummary])
def list_threads(
    project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    project = get_project_or_404(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")

    messages = (
        db.query(Message)
        .filter(Message.project_id == project_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    latest_by_counterpart: dict[int, Message] = {}
    for m in messages:
        counterpart_id = m.recipient_id if m.sender_id == user.id else m.sender_id
        latest_by_counterpart[counterpart_id] = m

    summaries = []
    for counterpart_id, m in latest_by_counterpart.items():
        counterpart = db.get(User, counterpart_id)
        if counterpart is None:
            continue
        summaries.append(
            {"counterpart": counterpart, "last_message": m.body, "last_message_at": m.created_at}
        )
    summaries.sort(key=lambda s: s["last_message_at"], reverse=True)
    return summaries

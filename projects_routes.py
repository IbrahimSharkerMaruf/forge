from fastapi import APIRouter, Depends, HTTPException, Query

import models
from auth import get_current_user, get_current_user_optional
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
    RatingRequest,
    ThreadSummary,
)

router = APIRouter()


def serialize_project(project: dict, viewer_id: str | None = None) -> dict:
    applicant_count = len(models.list_applications(project_id=project["id"]))
    owner = models.get_user(project["owner_id"])
    ratings = project.get("ratings") or {}
    avg_rating = round(sum(ratings.values()) / len(ratings), 1) if ratings else None
    return {
        "id": project["id"],
        "owner": owner,
        "title": project["title"],
        "description": project["description"],
        "skills": [s.strip() for s in project["skills"].split(",") if s.strip()],
        "status": project["status"],
        "created_at": project["created_at"],
        "applicant_count": applicant_count,
        "avg_rating": avg_rating,
        "rating_count": len(ratings),
        "my_rating": ratings.get(viewer_id) if viewer_id else None,
    }


def serialize_application(a: dict) -> dict:
    return {
        "id": a["id"],
        "project_id": a["project_id"],
        "applicant": models.get_user(a["applicant_id"]),
        "message": a["message"],
        "status": a["status"],
        "created_at": a["created_at"],
    }


def get_project_or_404(project_id: str) -> dict:
    project = models.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects", response_model=ProjectOut)
def create_project(req: ProjectCreate, user: dict = Depends(get_current_user)):
    skills = ", ".join(s.strip() for s in req.skills if s.strip())
    project = models.create_project(
        owner_id=user["id"], title=req.title, description=req.description, skills=skills
    )
    return serialize_project(project, viewer_id=user["id"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    status: str | None = None,
    mine: bool = False,
    applied: bool = False,
    collaborating: bool = False,
    user: dict | None = Depends(get_current_user_optional),
):
    owner_id = None
    ids = None

    if mine:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        owner_id = user["id"]
    if applied:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        ids = [a["project_id"] for a in models.list_applications(applicant_id=user["id"])]
    if collaborating:
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        ids = [
            a["project_id"]
            for a in models.list_applications(applicant_id=user["id"], status="accepted")
        ]

    projects = models.list_projects(status=status, owner_id=owner_id, ids=ids)
    viewer_id = user["id"] if user else None
    return [serialize_project(p, viewer_id=viewer_id) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, user: dict | None = Depends(get_current_user_optional)):
    project = get_project_or_404(project_id)
    data = serialize_project(project, viewer_id=user["id"] if user else None)

    credited = []
    if project["status"] == "completed":
        credited.append(data["owner"])
        accepted = models.list_applications(project_id=project["id"], status="accepted")
        for a in accepted:
            applicant = models.get_user(a["applicant_id"])
            if applicant:
                credited.append(applicant)
    data["credited"] = credited

    data["my_application"] = None
    data["applications"] = None
    if user:
        if user["id"] == project["owner_id"]:
            apps = models.list_applications(project_id=project["id"])
            data["applications"] = [serialize_application(a) for a in apps]
        else:
            my_apps = models.list_applications(project_id=project["id"], applicant_id=user["id"])
            data["my_application"] = serialize_application(my_apps[0]) if my_apps else None

    return data


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, req: ProjectUpdate, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    if project["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")

    fields = {}
    if req.title is not None:
        fields["title"] = req.title
    if req.description is not None:
        fields["description"] = req.description
    if req.skills is not None:
        fields["skills"] = ", ".join(s.strip() for s in req.skills if s.strip())
    if req.status is not None:
        if req.status not in ("open", "completed"):
            raise HTTPException(status_code=400, detail="Status must be 'open' or 'completed'")
        fields["status"] = req.status

    project = models.update_project(project, **fields)
    return serialize_project(project, viewer_id=user["id"])


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    if project["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the project owner can do this")
    models.delete_applications_for_project(project_id)
    models.delete_messages_for_project(project_id)
    models.delete_project(project_id)


@router.post("/projects/{project_id}/rate", response_model=ProjectOut)
def rate_project(project_id: str, req: RatingRequest, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    if project["owner_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You can't rate your own project")
    project = models.rate_project(project, user["id"], req.stars)
    return serialize_project(project, viewer_id=user["id"])


@router.post("/projects/{project_id}/apply", response_model=ApplicationOut)
def apply_to_project(project_id: str, req: ApplicationCreate, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    if project["owner_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You can't apply to your own project")
    if project["status"] != "open":
        raise HTTPException(status_code=400, detail="This project isn't accepting applicants")

    existing = models.list_applications(project_id=project_id, applicant_id=user["id"])
    if existing:
        raise HTTPException(status_code=400, detail="You already applied to this project")

    application = models.create_application(
        project_id=project_id, applicant_id=user["id"], message=req.message
    )
    return serialize_application(application)


@router.patch("/projects/{project_id}/applications/{application_id}", response_model=ApplicationOut)
def update_application(
    project_id: str,
    application_id: str,
    req: ApplicationUpdate,
    user: dict = Depends(get_current_user),
):
    project = get_project_or_404(project_id)
    if project["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")
    if req.status not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'accepted' or 'rejected'")

    application = models.get_application(application_id)
    if application is None or application["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Application not found")

    application = models.update_application(application, status=req.status)
    return serialize_application(application)


def assert_can_message(project: dict, user: dict, counterpart_id: str) -> None:
    if user["id"] == counterpart_id:
        raise HTTPException(status_code=400, detail="Can't message yourself")
    if user["id"] == project["owner_id"]:
        has_application = models.list_applications(
            project_id=project["id"], applicant_id=counterpart_id
        )
        if not has_application:
            raise HTTPException(status_code=403, detail="That person hasn't applied to this project")
    elif counterpart_id != project["owner_id"]:
        raise HTTPException(status_code=403, detail="You can only message the project owner")


@router.get("/projects/{project_id}/messages", response_model=list[MessageOut])
def get_messages(
    project_id: str,
    with_: str | None = Query(default=None, alias="with"),
    user: dict = Depends(get_current_user),
):
    project = get_project_or_404(project_id)
    counterpart_id = with_ if with_ is not None else project["owner_id"]
    assert_can_message(project, user, counterpart_id)

    all_messages = models.list_messages_for_project(project_id)
    return [
        m
        for m in all_messages
        if (m["sender_id"] == user["id"] and m["recipient_id"] == counterpart_id)
        or (m["sender_id"] == counterpart_id and m["recipient_id"] == user["id"])
    ]


@router.post("/projects/{project_id}/messages", response_model=MessageOut)
def send_message(project_id: str, req: MessageCreate, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    assert_can_message(project, user, req.recipient_id)
    return models.create_message(
        project_id=project_id, sender_id=user["id"], recipient_id=req.recipient_id, body=req.body
    )


@router.get("/projects/{project_id}/threads", response_model=list[ThreadSummary])
def list_threads(project_id: str, user: dict = Depends(get_current_user)):
    project = get_project_or_404(project_id)
    if project["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the project owner can do this")

    messages = models.list_messages_for_project(project_id)
    latest_by_counterpart: dict[str, dict] = {}
    for m in messages:
        counterpart_id = m["recipient_id"] if m["sender_id"] == user["id"] else m["sender_id"]
        latest_by_counterpart[counterpart_id] = m

    summaries = []
    for counterpart_id, m in latest_by_counterpart.items():
        counterpart = models.get_user(counterpart_id)
        if counterpart is None:
            continue
        summaries.append(
            {"counterpart": counterpart, "last_message": m["body"], "last_message_at": m["created_at"]}
        )
    summaries.sort(key=lambda s: s["last_message_at"], reverse=True)
    return summaries

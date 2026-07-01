"""
models.py -- all database reads and writes go through here.

I decided not to use an ORM. Every document is a plain Python dict stored as
JSON in Cosmos DB. The route files never touch the database containers directly --
they always call one of these functions. This keeps the database logic in one place.
"""

import uuid
from datetime import datetime, timezone

from db import applications_container, messages_container, projects_container, users_container


def new_id() -> str:
    # I use UUID4 to generate a random unique ID for every new document.
    return str(uuid.uuid4())


def now_iso() -> str:
    # I always store timestamps in UTC so they sort correctly as strings.
    return datetime.now(timezone.utc).isoformat()


# ---------- Users ----------


def create_user(name: str, email: str, password_hash: str, role: str = "user") -> dict:
    # I store the hashed password, never the plain text.
    # Role defaults to "user" -- accounts only become admin if I manually promote them.
    user = {
        "id": new_id(),
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "role": role,
        "github_url": None,
        "linkedin_url": None,
        "is_banned": False,
        "created_at": now_iso(),
    }
    users_container.create_item(user)
    return user


def get_user(user_id: str) -> dict | None:
    # read_item is the fastest lookup in Cosmos -- direct by ID and partition key.
    # I return None instead of raising an exception if the user doesn't exist.
    try:
        return users_container.read_item(item=user_id, partition_key=user_id)
    except Exception:
        return None


def get_user_by_email(email: str) -> dict | None:
    # I use this during login to find the account by email address.
    # I use a parameterised query (@email) to prevent SQL injection.
    # I need enable_cross_partition_query because I'm searching by email,
    # not by the partition key (which is id).
    results = list(
        users_container.query_items(
            query="SELECT * FROM c WHERE c.email = @email",
            parameters=[{"name": "@email", "value": email}],
            enable_cross_partition_query=True,
        )
    )
    return results[0] if results else None


def update_user(user: dict, **fields) -> dict:
    # Cosmos DB doesn't support partial field updates -- I always have to send
    # the entire document back. So I update the dict in memory first, then replace.
    user.update(fields)
    users_container.replace_item(item=user["id"], body=user)
    return user


def list_all_users() -> list[dict]:
    # Admin-only -- returns every user sorted by when they joined.
    users = list(
        users_container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True)
    )
    users.sort(key=lambda u: u["created_at"])
    return users


def delete_user(user_id: str) -> None:
    users_container.delete_item(item=user_id, partition_key=user_id)


# ---------- Projects ----------


def create_project(owner_id: str, title: str, description: str, skills: str) -> dict:
    project = {
        "id": new_id(),
        "owner_id": owner_id,
        "title": title,
        "description": description,
        "skills": skills,
        "status": "open",
        # I store ratings as a dict of {user_id: stars} directly inside the
        # project document. This means I don't need a separate container or
        # any kind of join to compute the average rating.
        "ratings": {},
        "created_at": now_iso(),
    }
    projects_container.create_item(project)
    return project


def rate_project(project: dict, user_id: str, stars: int) -> dict:
    # setdefault handles projects that existed before I added the ratings feature --
    # if there's no ratings field yet, it gets created as an empty dict.
    # One user gets one rating; if they rate again it just overwrites the old value.
    ratings = project.setdefault("ratings", {})
    ratings[user_id] = stars
    projects_container.replace_item(item=project["id"], body=project)
    return project


def get_project(project_id: str) -> dict | None:
    try:
        return projects_container.read_item(item=project_id, partition_key=project_id)
    except Exception:
        return None


def update_project(project: dict, **fields) -> dict:
    project.update(fields)
    projects_container.replace_item(item=project["id"], body=project)
    return project


def list_projects(
    status: str | None = None, owner_id: str | None = None, ids: list[str] | None = None
) -> list[dict]:
    # I build the query dynamically depending on which filters are provided.
    # All values go through parameterised queries to prevent injection.
    conditions = []
    parameters = []
    if status:
        conditions.append("c.status = @status")
        parameters.append({"name": "@status", "value": status})
    if owner_id:
        conditions.append("c.owner_id = @owner_id")
        parameters.append({"name": "@owner_id", "value": owner_id})
    if ids is not None:
        # ids=[] means the user applied to no projects -- return early rather than
        # running a query with an empty IN clause, which would be a syntax error.
        if not ids:
            return []
        id_params = [f"@id{i}" for i in range(len(ids))]
        conditions.append(f"c.id IN ({', '.join(id_params)})")
        parameters.extend({"name": p, "value": v} for p, v in zip(id_params, ids))

    query = "SELECT * FROM c"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    projects = list(
        projects_container.query_items(
            query=query, parameters=parameters, enable_cross_partition_query=True
        )
    )
    # I sort in Python rather than in the query because Cosmos doesn't
    # guarantee ordering without an ORDER BY clause on an indexed field.
    projects.sort(key=lambda p: p["created_at"], reverse=True)
    return projects


def delete_project(project_id: str) -> None:
    projects_container.delete_item(item=project_id, partition_key=project_id)


# ---------- Applications ----------


def create_application(project_id: str, applicant_id: str, message: str) -> dict:
    application = {
        "id": new_id(),
        "project_id": project_id,
        "applicant_id": applicant_id,
        "message": message,
        # Every application starts as pending -- the project owner moves it
        # to accepted or rejected.
        "status": "pending",
        "created_at": now_iso(),
    }
    applications_container.create_item(application)
    return application


def get_application(application_id: str) -> dict | None:
    try:
        return applications_container.read_item(item=application_id, partition_key=application_id)
    except Exception:
        return None


def update_application(application: dict, **fields) -> dict:
    application.update(fields)
    applications_container.replace_item(item=application["id"], body=application)
    return application


def list_applications(
    project_id: str | None = None, applicant_id: str | None = None, status: str | None = None
) -> list[dict]:
    # Same dynamic query pattern as list_projects -- I combine whichever filters are given.
    conditions = []
    parameters = []
    if project_id:
        conditions.append("c.project_id = @project_id")
        parameters.append({"name": "@project_id", "value": project_id})
    if applicant_id:
        conditions.append("c.applicant_id = @applicant_id")
        parameters.append({"name": "@applicant_id", "value": applicant_id})
    if status:
        conditions.append("c.status = @status")
        parameters.append({"name": "@status", "value": status})

    query = "SELECT * FROM c"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    return list(
        applications_container.query_items(
            query=query, parameters=parameters, enable_cross_partition_query=True
        )
    )


def delete_applications_for_project(project_id: str) -> None:
    # I call this when deleting a project so I don't leave orphaned
    # application records in the container.
    for app in list_applications(project_id=project_id):
        applications_container.delete_item(item=app["id"], partition_key=app["id"])


# ---------- Messages ----------


def create_message(project_id: str, sender_id: str, recipient_id: str, body: str) -> dict:
    # Messages are always scoped to a project -- you can only message someone
    # in the context of a specific project, not as general direct messages.
    message = {
        "id": new_id(),
        "project_id": project_id,
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "body": body,
        "created_at": now_iso(),
    }
    messages_container.create_item(message)
    return message


def list_messages_for_project(project_id: str) -> list[dict]:
    # I fetch all messages for the project here, then filter by conversation
    # pair in the route layer. This keeps the query simple.
    messages = list(
        messages_container.query_items(
            query="SELECT * FROM c WHERE c.project_id = @project_id",
            parameters=[{"name": "@project_id", "value": project_id}],
            enable_cross_partition_query=True,
        )
    )
    # Sort oldest first so the chat displays in the correct order.
    messages.sort(key=lambda m: m["created_at"])
    return messages


def delete_messages_for_project(project_id: str) -> None:
    # Clean up all messages when a project is deleted.
    for m in list_messages_for_project(project_id):
        messages_container.delete_item(item=m["id"], partition_key=m["id"])

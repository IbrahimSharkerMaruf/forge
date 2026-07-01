"""
schemas.py -- defines the shape of data going in and out of the API.

I use Pydantic for this. FastAPI uses these classes to validate incoming
requests automatically (wrong type or missing field returns a 422 error)
and to control exactly which fields appear in each response.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------

class SignupRequest(BaseModel):
    # Field constraints are enforced automatically by FastAPI.
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr  # EmailStr validates the format, not just that it's a string
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    # This is what gets returned to the user after login or signup.
    access_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    # All fields are optional -- users can update any subset of their profile.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    github_url: str | None = None
    linkedin_url: str | None = None


class UserOut(BaseModel):
    # Full user record -- returned when a user views their own profile or an admin views users.
    # password_hash is never included because I only declare the fields I want to expose.
    id: str
    name: str
    email: EmailStr
    role: str
    github_url: str | None
    linkedin_url: str | None
    is_banned: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PublicProfile(BaseModel):
    # Reduced version of the user record for showing to other users.
    # I deliberately left out email and is_banned -- other users don't need to see those.
    id: str
    name: str
    role: str
    github_url: str | None
    linkedin_url: str | None

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    # Lets admins change someone's role or ban/unban them.
    role: str | None = None   # "user" | "admin"
    is_banned: bool | None = None


# ---------- Applications ----------

class ApplicationOut(BaseModel):
    id: str
    project_id: str
    applicant: PublicProfile
    message: str
    status: str   # "pending" | "accepted" | "rejected"
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ApplicationUpdate(BaseModel):
    # Only the project owner calls this to accept or reject an application.
    status: str  # "accepted" | "rejected"


# ---------- Projects ----------

class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    # All fields optional because this is a PATCH, not a PUT.
    # Only the fields I send get updated.
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1)
    skills: list[str] | None = None
    status: str | None = None  # "open" | "completed"


class ProjectOut(BaseModel):
    # Standard project response used in list views and after create/update.
    id: str
    owner: PublicProfile
    title: str
    description: str
    skills: list[str]
    status: str
    created_at: datetime
    applicant_count: int = 0
    # I use None for avg_rating when there are no ratings yet, not 0,
    # so the frontend can tell the difference between "no ratings" and "rated zero".
    avg_rating: float | None = None
    rating_count: int = 0
    # my_rating is the current viewer's own star value, or None if they haven't rated.
    my_rating: int | None = None

    class Config:
        from_attributes = True


class RatingRequest(BaseModel):
    # ge=1, le=5 enforces the 1-5 star range.
    # FastAPI automatically returns a 422 if someone sends a value outside this.
    stars: int = Field(ge=1, le=5)


class ProjectDetail(ProjectOut):
    # Extended version of ProjectOut for the individual project page.
    # I inherit all the fields from ProjectOut and add these three.
    credited: list[PublicProfile] = Field(default_factory=list)
    my_application: ApplicationOut | None = None
    # applications is None for non-owners, not an empty list.
    # The frontend uses this distinction to decide what to show.
    applications: list[ApplicationOut] | None = None


# ---------- Messages ----------

class MessageCreate(BaseModel):
    recipient_id: str
    body: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: str
    sender_id: str
    recipient_id: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadSummary(BaseModel):
    # Used in the message inbox to show the other person and a preview of the last message.
    counterpart: PublicProfile
    last_message: str
    last_message_at: datetime

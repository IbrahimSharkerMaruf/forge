from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    github_url: str | None = None
    linkedin_url: str | None = None


class UserOut(BaseModel):
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
    id: str
    name: str
    role: str
    github_url: str | None
    linkedin_url: str | None

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    role: str | None = None  # "user" | "admin"
    is_banned: bool | None = None


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1)
    skills: list[str] | None = None
    status: str | None = None  # "open" | "completed"


class ApplicationOut(BaseModel):
    id: str
    project_id: str
    applicant: PublicProfile
    message: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: str
    owner: PublicProfile
    title: str
    description: str
    skills: list[str]
    status: str
    created_at: datetime
    applicant_count: int = 0
    avg_rating: float | None = None
    rating_count: int = 0
    my_rating: int | None = None

    class Config:
        from_attributes = True


class RatingRequest(BaseModel):
    stars: int = Field(ge=1, le=5)


class ProjectDetail(ProjectOut):
    credited: list[PublicProfile] = Field(default_factory=list)
    my_application: ApplicationOut | None = None
    applications: list[ApplicationOut] | None = None  # only populated for the owner


class ApplicationCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ApplicationUpdate(BaseModel):
    status: str  # "accepted" | "rejected"


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
    counterpart: PublicProfile
    last_message: str
    last_message_at: datetime

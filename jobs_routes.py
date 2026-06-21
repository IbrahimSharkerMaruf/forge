"""Adzuna job-listing integration -- suggests real, live job listings related
to a salary prediction's job title.

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY (free at https://developer.adzuna.com/)
set as environment variables. Never hardcode these: they're tied to a personal
account and rate-limited. Put them in a local .env file (gitignored) or export
them in your shell before running uvicorn.
"""

import os

import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_COUNTRY = "gb"


@router.get("/jobs/similar")
def get_similar_jobs(job_title: str, country: str = DEFAULT_COUNTRY):
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        raise HTTPException(
            status_code=503,
            detail="Job listings aren't configured yet -- set ADZUNA_APP_ID and ADZUNA_APP_KEY.",
        )

    try:
        response = requests.get(
            f"{ADZUNA_BASE_URL}/{country}/search/1",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": job_title,
                "results_per_page": 15,
                "content-type": "application/json",
            },
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach Adzuna: {e}")

    data = response.json()
    listings = [
        {
            "title": job.get("title"),
            "company": (job.get("company") or {}).get("display_name"),
            "location": (job.get("location") or {}).get("display_name"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "url": job.get("redirect_url"),
            "created": job.get("created"),
        }
        for job in data.get("results", [])
    ]
    return {"count": data.get("count", 0), "listings": listings}

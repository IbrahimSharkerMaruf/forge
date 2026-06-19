from catboost import CatBoostRegressor, Pool
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

from auth_routes import router as auth_router
from projects_routes import router as projects_router
from db import Base, engine
import models  # noqa: F401 -- registers User with Base before create_all

MAE = 11576  # from salary.ipynb evaluation, used to show a likely range around the point estimate
CAT_FEATURE_INDICES = [1, 2, 3]  # Gender, Education Level, Job Title

model = CatBoostRegressor()
model.load_model("salary_model.cbm")

job_titles_df = pd.read_csv("Salary_Data_larger.csv")
JOB_TITLES = sorted(
    job_titles_df["Job Title"].dropna().astype(str).str.strip().loc[lambda s: s != ""].unique()
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Forge Salary Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)


class PredictRequest(BaseModel):
    age: int
    gender: str
    education: str
    job_title: str
    experience: int


@app.get("/job-titles")
def get_job_titles():
    return JOB_TITLES


@app.post("/predict")
def predict(req: PredictRequest):
    if req.job_title not in JOB_TITLES:
        raise HTTPException(status_code=400, detail="Unknown job title")
    if req.experience > max(0, req.age - 18):
        raise HTTPException(status_code=400, detail="Experience can't exceed age - 18")

    row = [[req.age, req.gender, req.education, req.job_title, req.experience]]
    prediction = float(model.predict(row)[0])

    pool = Pool(row, cat_features=CAT_FEATURE_INDICES)
    shap_values = model.get_feature_importance(pool, type="ShapValues")[0]
    contributions = dict(zip(model.feature_names_, shap_values[:-1]))

    bar_features = ["Job Title", "Years of Experience", "Education Level"]
    max_abs = max(abs(contributions[f]) for f in bar_features) or 1
    bars = [
        {"label": label, "pct": round(abs(contributions[feature]) / max_abs * 100)}
        for feature, label in zip(
            bar_features, ["Job title", "Experience", "Education"]
        )
    ]

    return {
        "prediction": round(prediction),
        "range_low": round(prediction - MAE),
        "range_high": round(prediction + MAE),
        "bars": bars,
    }


# Serves the whole Front/ folder on this same origin (http://localhost:8000/...) so
# localStorage-based login persists across pages -- file:// pages are isolated origins.
app.mount("/", StaticFiles(directory="Front", html=True), name="frontend")

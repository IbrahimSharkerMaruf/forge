import numpy as np
from catboost import CatBoostRegressor, Pool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

load_dotenv()  # picks up a local .env file (gitignored) for secrets like ADZUNA_APP_ID

from auth_routes import router as auth_router
from projects_routes import router as projects_router
from insights_routes import router as insights_router, _load_cleaned_data
from jobs_routes import router as jobs_router

MAE = 11576  # from salary.ipynb evaluation, used to show a likely range around the point estimate
CAT_FEATURE_INDICES = [1, 2, 3]  # Gender, Education Level, Job Title
FEATURE_LABELS = {
    "Age": "Age",
    "Gender": "Gender",
    "Education Level": "Education",
    "Job Title": "Job title",
    "Years of Experience": "Experience",
}

model = CatBoostRegressor()
model.load_model("salary_model.cbm")

job_titles_df = pd.read_csv("Salary_Data_larger.csv")
JOB_TITLES = sorted(
    job_titles_df["Job Title"].dropna().astype(str).str.strip().loc[lambda s: s != ""].unique()
)

CLEANED_DATA = _load_cleaned_data()

app = FastAPI(title="Forge Salary Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(insights_router)
app.include_router(jobs_router)


class PredictRequest(BaseModel):
    age: int
    gender: str
    education: str
    job_title: str
    experience: int


def _validate_inputs(job_title: str, age: int, experience: int) -> None:
    if job_title not in JOB_TITLES:
        raise HTTPException(status_code=400, detail="Unknown job title")
    if experience > max(0, age - 18):
        raise HTTPException(status_code=400, detail="Experience can't exceed age - 18")


EDUCATION_LEVELS = ["High School", "Bachelor", "Master", "PhD"]


def _build_counterfactuals(
    age: int, gender: str, education: str, job_title: str, experience: int, base_prediction: float
) -> list[dict]:
    """Counterfactual explanations: re-run the same prediction with exactly one
    input changed, so the effect of that single change is isolated and concrete
    -- a different (and more intuitive) explainability technique than SHAP."""
    scenarios = []

    if experience + 2 <= max(0, age - 18):
        pred, _ = _predict_with_contributions(age, gender, education, job_title, experience + 2)
        scenarios.append(
            {"label": "With 2 more years of experience", "prediction": round(pred), "delta": round(pred - base_prediction)}
        )

    if education in EDUCATION_LEVELS:
        idx = EDUCATION_LEVELS.index(education)
        if idx < len(EDUCATION_LEVELS) - 1:
            next_edu = EDUCATION_LEVELS[idx + 1]
            pred, _ = _predict_with_contributions(age, gender, next_edu, job_title, experience)
            scenarios.append(
                {"label": f"With a {next_edu}'s instead of {education}'s", "prediction": round(pred), "delta": round(pred - base_prediction)}
            )

    pred, _ = _predict_with_contributions(age + 5, gender, education, job_title, experience)
    scenarios.append(
        {"label": "5 years older (same experience)", "prediction": round(pred), "delta": round(pred - base_prediction)}
    )

    other_gender = "Female" if gender.lower() == "male" else "Male"
    pred, _ = _predict_with_contributions(age, other_gender, education, job_title, experience)
    scenarios.append(
        {
            "label": f"Labeled {other_gender.lower()} instead of {gender.lower()} (everything else identical)",
            "prediction": round(pred),
            "delta": round(pred - base_prediction),
        }
    )

    return scenarios


def _predict_with_contributions(age: int, gender: str, education: str, job_title: str, experience: int):
    # The model was trained on lowercased Gender/Job Title strings (see salary.ipynb's
    # cleaning step) -- CatBoost's categorical matching is case-sensitive, so passing
    # the dropdown's original casing ("Male", "Software Engineer") silently fed it
    # out-of-vocabulary categories and collapsed every job title to ~the same prediction.
    row = [[age, gender.lower().strip(), education, job_title.lower().strip(), experience]]
    prediction = float(model.predict(row)[0])

    pool = Pool(row, cat_features=CAT_FEATURE_INDICES)
    shap_values = model.get_feature_importance(pool, type="ShapValues")[0]
    contributions = dict(zip(model.feature_names_, shap_values[:-1]))
    return prediction, contributions


@app.get("/job-titles")
def get_job_titles():
    return JOB_TITLES


@app.post("/predict")
def predict(req: PredictRequest):
    _validate_inputs(req.job_title, req.age, req.experience)
    prediction, contributions = _predict_with_contributions(
        req.age, req.gender, req.education, req.job_title, req.experience
    )

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


@app.get("/predict/details")
def predict_details(age: int, gender: str, education: str, job_title: str, experience: int):
    _validate_inputs(job_title, age, experience)
    prediction, contributions = _predict_with_contributions(age, gender, education, job_title, experience)

    breakdown = sorted(
        (
            {"feature": FEATURE_LABELS[f], "value": round(v), "direction": "up" if v >= 0 else "down"}
            for f, v in contributions.items()
        ),
        key=lambda b: abs(b["value"]),
        reverse=True,
    )

    salaries = CLEANED_DATA["Salary"].values
    percentile = round(float((salaries < prediction).mean() * 100), 1)

    bin_count = 20
    counts, edges = np.histogram(salaries, bins=bin_count)
    predicted_bin = min(int(np.searchsorted(edges, prediction, side="right") - 1), bin_count - 1)
    predicted_bin = max(predicted_bin, 0)
    histogram = [
        {"range_low": round(edges[i]), "range_high": round(edges[i + 1]), "count": int(counts[i])}
        for i in range(bin_count)
    ]

    same_title = CLEANED_DATA[CLEANED_DATA["Job Title"] == job_title.lower().strip()]
    job_stats = None
    if len(same_title) > 0:
        job_stats = {
            "count": int(len(same_title)),
            "mean": round(float(same_title["Salary"].mean())),
            "min": round(float(same_title["Salary"].min())),
            "max": round(float(same_title["Salary"].max())),
        }

    counterfactuals = _build_counterfactuals(age, gender, education, job_title, experience, prediction)

    return {
        "prediction": round(prediction),
        "range_low": round(prediction - MAE),
        "range_high": round(prediction + MAE),
        "breakdown": breakdown,
        "percentile": percentile,
        "histogram": histogram,
        "predicted_bin": predicted_bin,
        "job_stats": job_stats,
        "counterfactuals": counterfactuals,
    }


# Serves the whole Front/ folder on this same origin (http://localhost:8000/...) so
# localStorage-based login persists across pages -- file:// pages are isolated origins.
app.mount("/", StaticFiles(directory="Front", html=True), name="frontend")

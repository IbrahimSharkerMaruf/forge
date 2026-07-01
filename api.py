import numpy as np
from catboost import CatBoostRegressor, Pool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

# I load environment variables first before importing anything else,
# because some modules read those variables at import time.
load_dotenv()

from auth_routes import router as auth_router
from projects_routes import router as projects_router
from insights_routes import router as insights_router, _load_cleaned_data
from jobs_routes import router as jobs_router

# MAE came from my notebook evaluation -- I use it to show a salary range
# around the prediction rather than pretending the model is perfectly accurate.
MAE = 11812

# I have to tell CatBoost which columns are categorical, not numeric.
# Indices 1 and 3 are Gender and Job Title.
# Education Level is now a numeric ordinal (0-3) so it is NOT in this list --
# that way CatBoost understands that Master (2) > Bachelor (1) > High School (0).
CAT_FEATURE_INDICES = [1, 3]

# I map the dataset column names to friendlier labels for the UI.
FEATURE_LABELS = {
    "Age": "Age",
    "Gender": "Gender",
    "Education Level": "Education",
    "Job Title": "Job title",
    "Years of Experience": "Experience",
}

# I load the model once at startup, not on every request.
# Loading from disk on every prediction would be far too slow.
model = CatBoostRegressor()
model.load_model("salary_model.cbm")

# I load the job titles from the CSV once at startup to validate form inputs.
job_titles_df = pd.read_csv("Salary_Data_larger.csv")
JOB_TITLES = sorted(
    job_titles_df["Job Title"].dropna().astype(str).str.strip().loc[lambda s: s != ""].unique()
)

# I also keep the cleaned dataset in memory for the /predict/details endpoint --
# it's used to compute percentile rank and histogram position on every request.
CLEANED_DATA = _load_cleaned_data()

app = FastAPI(title="Forge Salary Predictor API")

# CORS lets the frontend call the API from the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# I split the API into four separate routers to keep things organised.
# Each router handles one part of the platform.
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(insights_router)
app.include_router(jobs_router)


# Pydantic validates the request body automatically.
# If any field is missing or the wrong type, FastAPI returns a 422 error.
class PredictRequest(BaseModel):
    age: int
    gender: str
    education: str
    job_title: str
    experience: int


def _validate_inputs(job_title: str, age: int, experience: int) -> None:
    # I reject job titles not in the training data because the model
    # has never seen them and would produce unreliable predictions.
    if job_title not in JOB_TITLES:
        raise HTTPException(status_code=400, detail="Unknown job title")
    # I also check that experience doesn't exceed age minus 18,
    # because you can't have worked longer than you've been an adult.
    if experience > max(0, age - 18):
        raise HTTPException(status_code=400, detail="Experience can't exceed age - 18")


# EDUCATION_LEVELS keeps the display strings in order so counterfactuals can
# find the next level up. EDUCATION_ORDER maps those strings to the integer
# the model receives -- ordinal encoding so the model knows Master > Bachelor.
EDUCATION_LEVELS = ["High School", "Bachelor", "Master", "PhD"]
EDUCATION_ORDER = {"High School": 0, "Bachelor": 1, "Master": 2, "PhD": 3}


def _build_counterfactuals(
    age: int, gender: str, education: str, job_title: str, experience: int, base_prediction: float
) -> list[dict]:
    """
    Counterfactual explanations are a different explainability technique from SHAP.
    Instead of breaking down the maths, I re-run the live model four times with
    exactly one input changed each time. The difference shows the isolated effect
    of that single variable, which is much more intuitive for users.
    """
    scenarios = []

    # Scenario 1: two more years of experience.
    # I only include this if it's logically valid given the user's age.
    if experience + 2 <= max(0, age - 18):
        pred, _ = _predict_with_contributions(age, gender, education, job_title, experience + 2)
        scenarios.append(
            {"label": "With 2 more years of experience", "prediction": round(pred), "delta": round(pred - base_prediction)}
        )

    # Scenario 2: next education level up (e.g. Bachelor to Master).
    # If the user already has a PhD, I skip this because there's nothing above it.
    if education in EDUCATION_LEVELS:
        idx = EDUCATION_LEVELS.index(education)
        if idx < len(EDUCATION_LEVELS) - 1:
            next_edu = EDUCATION_LEVELS[idx + 1]
            pred, _ = _predict_with_contributions(age, gender, next_edu, job_title, experience)
            scenarios.append(
                {"label": f"With a {next_edu}'s instead of {education}'s", "prediction": round(pred), "delta": round(pred - base_prediction)}
            )

    # Scenario 3: five years older with the same experience.
    # This isolates the effect of age alone, separate from extra experience gained.
    pred, _ = _predict_with_contributions(age + 5, gender, education, job_title, experience)
    scenarios.append(
        {"label": "5 years older (same experience)", "prediction": round(pred), "delta": round(pred - base_prediction)}
    )

    # Scenario 4: gender label flipped, everything else identical.
    # This directly shows the pay gap the model learned from the training data.
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
    # Gender and Job Title are lowercased strings (CatBoost handles them).
    # Education Level is an ordinal int (0-3) so the model understands the ordering.
    edu_ordinal = EDUCATION_ORDER.get(education, 1)

    # Some job titles have very few Master's/PhD examples in training data, so the raw
    # model prediction can be non-monotone (Master < Bachelor for Software Engineer etc.).
    # I enforce monotonicity by predicting for every lower education level too and
    # returning the maximum. The SHAP values come from whichever level won, so they
    # remain internally consistent with the salary shown to the user.
    best_pred = None
    best_row = None
    for edu in range(edu_ordinal + 1):
        r = [[age, gender.lower().strip(), edu, job_title.lower().strip(), experience]]
        p = float(model.predict(r)[0])
        if best_pred is None or p > best_pred:
            best_pred = p
            best_row = r

    # TreeSHAP gives me a contribution value for each feature for this specific prediction.
    # It's not global feature importance -- it tells me how much each input pushed
    # this particular person's salary up or down from the model's average baseline.
    pool = Pool(best_row, cat_features=CAT_FEATURE_INDICES)
    shap_values = model.get_feature_importance(pool, type="ShapValues")[0]
    # The last element is the baseline value, not a feature -- I drop it.
    contributions = dict(zip(model.feature_names_, shap_values[:-1]))
    return best_pred, contributions


@app.get("/job-titles")
def get_job_titles():
    # Returns the full list of job titles for the dropdown.
    # Already loaded into memory at startup so no disk read happens here.
    return JOB_TITLES


@app.post("/predict")
def predict(req: PredictRequest):
    # Quick prediction for the landing page -- returns the salary and a
    # simplified three-bar breakdown showing the top contributing features.
    _validate_inputs(req.job_title, req.age, req.experience)
    prediction, contributions = _predict_with_contributions(
        req.age, req.gender, req.education, req.job_title, req.experience
    )

    # I normalise the three features to a 0-100 scale for the bar chart.
    # The or 1 prevents division by zero if all contributions happen to be zero.
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
        # I use MAE from my notebook to show an honest range, not false precision.
        "range_low": round(prediction - MAE),
        "range_high": round(prediction + MAE),
        "bars": bars,
    }


@app.get("/predict/details")
def predict_details(age: int, gender: str, education: str, job_title: str, experience: int):
    # Full explainability endpoint for the result page.
    # More expensive than /predict because I compute SHAP values, a histogram,
    # percentile rank, job-title comparison stats, and four counterfactual scenarios.
    _validate_inputs(job_title, age, experience)
    prediction, contributions = _predict_with_contributions(age, gender, education, job_title, experience)

    # I sort all five SHAP values by absolute size so the biggest impact shows first.
    breakdown = sorted(
        (
            {"feature": FEATURE_LABELS[f], "value": round(v), "direction": "up" if v >= 0 else "down"}
            for f, v in contributions.items()
        ),
        key=lambda b: abs(b["value"]),
        reverse=True,
    )

    # Percentile: what fraction of the 1,787 training salaries are below this prediction.
    salaries = CLEANED_DATA["Salary"].values
    percentile = round(float((salaries < prediction).mean() * 100), 1)

    # I build a 20-bin histogram so the frontend can highlight which bin
    # this prediction falls into on the distribution chart.
    bin_count = 20
    counts, edges = np.histogram(salaries, bins=bin_count)
    predicted_bin = min(int(np.searchsorted(edges, prediction, side="right") - 1), bin_count - 1)
    predicted_bin = max(predicted_bin, 0)
    histogram = [
        {"range_low": round(edges[i]), "range_high": round(edges[i + 1]), "count": int(counts[i])}
        for i in range(bin_count)
    ]

    # Compare against real salaries in the training data for the same job title.
    # I use lowercase here for the same reason as in _predict_with_contributions.
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


@app.get("/")
def root():
    # Without this, visiting the bare Azure domain returns 404 because
    # the static mount below only handles paths it recognises, and I don't
    # have an index.html -- the landing page is forge_landing_page.html.
    return FileResponse("Front/forge_landing_page.html")


# I mount the entire Front/ folder as static files on the same origin so that
# localStorage-based JWT tokens work across all pages. If pages were served
# from file://, each page would be a different origin and localStorage would
# be isolated between them -- login would break every time you navigated.
app.mount("/", StaticFiles(directory="Front", html=True), name="frontend")

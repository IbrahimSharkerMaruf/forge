"""Model evaluation endpoints: comparison against other algorithms, residuals,
and a gender bias check. Everything here is computed once at server startup
from the same cleaned dataset and train/test split used in salary.ipynb
(random_state=42, test_size=0.2), then cached -- it's read-only analysis, not
something that needs to run per-request.
"""

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from fastapi import APIRouter
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from xgboost import XGBRegressor

router = APIRouter()

CAT_COLS = ["Gender", "Education Level", "Job Title"]


def _load_cleaned_data() -> pd.DataFrame:
    df = pd.read_csv("Salary_Data_larger.csv").dropna()
    for col in CAT_COLS:
        df[col] = df[col].astype("string").str.lower().str.strip()
    df = df.drop_duplicates()
    df["Education Level"] = df["Education Level"].replace(
        {
            "phd": "PhD",
            "master's degree": "Master",
            "master's": "Master",
            "bachelor's degree": "Bachelor",
            "bachelor's": "Bachelor",
            "high school": "High School",
        }
    )
    return df


def _compute_insights() -> dict:
    df = _load_cleaned_data()
    x = df.drop(columns=["Salary"])
    y = df["Salary"]
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

    cat_model = CatBoostRegressor(loss_function="RMSE", verbose=False)
    cat_model.fit(x_train, y_train, cat_features=CAT_COLS)
    cat_pred = cat_model.predict(x_test)

    x_train_enc = pd.get_dummies(x_train, columns=CAT_COLS)
    x_test_enc = pd.get_dummies(x_test, columns=CAT_COLS).reindex(columns=x_train_enc.columns, fill_value=0)

    rf = RandomForestRegressor(n_estimators=300, random_state=42)
    rf.fit(x_train_enc, y_train)
    rf_pred = rf.predict(x_test_enc)

    xgb = XGBRegressor(n_estimators=300, random_state=42)
    xgb.fit(x_train_enc, y_train)
    xgb_pred = xgb.predict(x_test_enc)

    comparison = [
        {"model": "CatBoost", "r2": r2_score(y_test, cat_pred), "mae": mean_absolute_error(y_test, cat_pred)},
        {"model": "Random Forest", "r2": r2_score(y_test, rf_pred), "mae": mean_absolute_error(y_test, rf_pred)},
        {"model": "XGBoost", "r2": r2_score(y_test, xgb_pred), "mae": mean_absolute_error(y_test, xgb_pred)},
    ]
    comparison.sort(key=lambda m: m["r2"], reverse=True)

    residuals = [
        {"actual": round(a), "predicted": round(p), "residual": round(a - p)}
        for a, p in zip(y_test.values, cat_pred)
    ]

    as_male = x_test.copy()
    as_male["Gender"] = "male"
    as_female = x_test.copy()
    as_female["Gender"] = "female"
    pred_male = cat_model.predict(as_male)
    pred_female = cat_model.predict(as_female)
    diff = pred_male - pred_female

    raw_by_gender = df[df["Gender"].isin(["male", "female"])].groupby("Gender")["Salary"].agg(["mean", "count"])

    bias = {
        "sample_size": len(x_test),
        "mean_pred_as_male": round(pred_male.mean()),
        "mean_pred_as_female": round(pred_female.mean()),
        "mean_diff": round(diff.mean()),
        "median_diff": round(float(np.median(diff))),
        "pct_male_higher": round((diff > 0).mean() * 100, 1),
        "raw_mean_male": round(raw_by_gender.loc["male", "mean"]),
        "raw_mean_female": round(raw_by_gender.loc["female", "mean"]),
        "raw_count_male": int(raw_by_gender.loc["male", "count"]),
        "raw_count_female": int(raw_by_gender.loc["female", "count"]),
    }

    importances = cat_model.get_feature_importance()
    feature_importance = sorted(
        (
            {"feature": name, "importance": round(float(imp), 2)}
            for name, imp in zip(cat_model.feature_names_, importances)
        ),
        key=lambda f: f["importance"],
        reverse=True,
    )

    kfold = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_scores = []
    for train_idx, val_idx in kfold.split(x):
        x_tr, x_val = x.iloc[train_idx], x.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
        fold_model = CatBoostRegressor(loss_function="RMSE", verbose=False)
        fold_model.fit(x_tr, y_tr, cat_features=CAT_COLS)
        fold_scores.append(r2_score(y_val, fold_model.predict(x_val)))

    cv_stability = {
        "fold_scores": [round(s, 4) for s in fold_scores],
        "mean": round(float(np.mean(fold_scores)), 4),
        "std": round(float(np.std(fold_scores)), 4),
    }

    return {
        "comparison": comparison,
        "residuals": residuals,
        "bias": bias,
        "feature_importance": feature_importance,
        "cv_stability": cv_stability,
    }


_INSIGHTS_CACHE: dict | None = None


def _get_insights() -> dict:
    # Computed lazily on first request rather than at import time -- training
    # 8 models (comparison + 5-fold CV) blocked app startup long enough to
    # exceed Azure's container startup probe timeout on a constrained tier.
    global _INSIGHTS_CACHE
    if _INSIGHTS_CACHE is None:
        _INSIGHTS_CACHE = _compute_insights()
    return _INSIGHTS_CACHE


@router.get("/insights/model-comparison")
def get_model_comparison():
    return _get_insights()["comparison"]


@router.get("/insights/residuals")
def get_residuals():
    return _get_insights()["residuals"]


@router.get("/insights/bias")
def get_bias():
    return _get_insights()["bias"]


@router.get("/insights/feature-importance")
def get_feature_importance():
    return _get_insights()["feature_importance"]


@router.get("/insights/cv-stability")
def get_cv_stability():
    return _get_insights()["cv_stability"]

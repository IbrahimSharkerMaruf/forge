"""
Retrains the salary model with Education Level encoded as an ordinal integer
(0=High School, 1=Bachelor, 2=Master, 3=PhD) instead of a string category.

Previously the model treated all education levels as unrelated labels, so it
could predict Master's < Bachelor's with no awareness that Master's implies
the Bachelor's was already completed. Ordinal encoding preserves the ordering,
and _predict_with_contributions in api.py enforces strict monotonicity at
prediction time by returning max(pred[current], pred[lower_edu]).
"""

import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

EDUCATION_ORDER = {"High School": 0, "Bachelor": 1, "Master": 2, "PhD": 3}

df = pd.read_csv("Salary_Data_larger.csv").dropna()
for col in ["Gender", "Education Level", "Job Title"]:
    df[col] = df[col].astype("string").str.lower().str.strip()
df = df.drop_duplicates()
df["Education Level"] = df["Education Level"].replace({
    "phd": "PhD",
    "master's degree": "Master",
    "master's": "Master",
    "bachelor's degree": "Bachelor",
    "bachelor's": "Bachelor",
    "high school": "High School",
})
df["Education Level"] = df["Education Level"].map(EDUCATION_ORDER)
df = df.dropna(subset=["Education Level"])
df["Education Level"] = df["Education Level"].astype(int)

print(f"Training rows: {len(df)}")
print("Education Level distribution:\n", df["Education Level"].value_counts().sort_index())

x = df.drop(columns=["Salary"])
y = df["Salary"]

x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

# Gender (index 1) and Job Title (index 3) are categorical.
# Education Level is now a numeric ordinal -- NOT in cat_features.
model = CatBoostRegressor(loss_function="RMSE", verbose=100)
model.fit(x_train, y_train, cat_features=["Gender", "Job Title"])

r2  = r2_score(y_test, model.predict(x_test))
mae = mean_absolute_error(y_test, model.predict(x_test))
print(f"\nR²:  {r2:.4f}")
print(f"MAE: {mae:.0f}")
print(f"Feature names: {model.feature_names_}")
print(f"Cat feature indices: {model.get_cat_feature_indices()}")

model.save_model("salary_model.cbm")
print("\nModel saved to salary_model.cbm")

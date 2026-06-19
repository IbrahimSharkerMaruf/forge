import streamlit as st
import pandas as pd
from catboost import CatBoostRegressor

# load trained model weights via this code
model = CatBoostRegressor()
model.load_model("salary_model.cbm")

st.title("💼 Salary Prediction App")

st.write("Enter employee information to predict salary!")


@st.cache_data
def load_job_titles():
    df = pd.read_csv("Salary_Data_larger.csv")
    titles = (
        df["Job Title"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s != ""]
        .unique()
    )
    return sorted(titles)


job_titles = load_job_titles()
job_title_placeholder = "Select a job title"
job_title_options = [job_title_placeholder] + job_titles

age = st.slider("Age", 18, 100, 25)

gender = st.selectbox("Gender", ["Male", "Female"])

education = st.selectbox(
    "Education Level",
    ["High School", "Bachelor", "Master", "PhD"]
)

job_title = st.selectbox("Job Title", job_title_options)

max_possible_experience = min(40, max(0, age - 18))
default_experience = min(10, max_possible_experience)
if max_possible_experience == 0:
    experience = st.number_input(
        "Years of Experience",
        min_value=0,
        max_value=0,
        value=0,
        step=1,
        disabled=True,
    )
    st.caption("At age 18, experience must be 0 years.")
else:
    experience = st.slider(
        "Years of Experience",
        0,
        max_possible_experience,
        default_experience,
    )

if st.button("Predict Salary"):
    if job_title == job_title_placeholder:
        st.warning("Please select a job title before predicting.")
    elif experience > max_possible_experience:
        st.error(
            f"Invalid input: for age {age}, max experience is {max_possible_experience} years."
        )
    else:
        data = [[age, gender, education, job_title, experience]]
        prediction = model.predict(data)
        st.success(f"💰 Predicted Salary: ${prediction[0]:,.2f}")
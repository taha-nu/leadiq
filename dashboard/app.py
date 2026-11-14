"""LeadIQ dashboard for sales teams.

Run locally:  streamlit run dashboard/app.py
It talks only to the scoring API (API_URL), so it works the same locally,
in docker-compose and on AWS.
"""
import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
BAND_COLORS = {"Hot": "#d9534f", "Warm": "#f0ad4e", "Cold": "#5bc0de"}

st.set_page_config(page_title="LeadIQ", page_icon="📈", layout="wide")
st.title("LeadIQ: lead scoring for sales")


def api(method: str, path: str, **kwargs):
    r = requests.request(method, f"{API_URL}{path}", timeout=60, **kwargs)
    r.raise_for_status()
    return r.json()


def send_feedback(pid: str, converted: bool) -> None:
    api("POST", "/feedback", json={"prediction_id": pid, "converted": converted})
    st.toast("Feedback saved, thanks!")


score_tab, pipeline_tab = st.tabs(["Score a lead", "Lead pipeline quality"])

# ---------------------------------------------------------------- score a lead
with score_tab:
    with st.form("lead"):
        c1, c2, c3 = st.columns(3)
        lead = {
            "lead_origin": c1.selectbox("Lead origin", ["Landing Page Submission", "API", "Lead Add Form", "Other"]),
            "lead_source": c1.selectbox("Lead source", ["Google", "Direct Traffic", "Olark Chat", "Organic Search",
                                                        "Reference", "Welingak Website", "Referral Sites", "Other"]),
            "last_activity": c1.selectbox("Last activity", ["Email Opened", "SMS Sent", "Olark Chat Conversation",
                                                            "Page Visited on Website", "Converted to Lead",
                                                            "Email Bounced", "Email Link Clicked",
                                                            "Form Submitted on Website", "Unreachable", "Other"]),
            "totalvisits": c2.number_input("Total visits", 0, 50, 3),
            "total_time_spent_on_website": c2.number_input("Time on website (seconds)", 0, 5000, 600),
            "page_views_per_visit": c2.number_input("Page views per visit", 0.0, 20.0, 2.5),
            "what_is_your_current_occupation": c3.selectbox(
                "Occupation", ["Unemployed", "Working Professional", "Student", "Unknown", "Other"]),
            "city": c3.selectbox("City", ["Mumbai", "Thane & Outskirts", "Other Cities of Maharashtra",
                                          "Other Metro Cities", "Other Cities", "Unknown"]),
            "do_not_email": int(c3.checkbox("Do not email")),
        }
        submitted = st.form_submit_button("Score lead", type="primary")

    if submitted:
        st.session_state["result"] = api("POST", "/predict", json=lead)

    result = st.session_state.get("result")
    if result:
        band = result["band"]
        m1, m2, m3 = st.columns(3)
        m1.markdown(f"### :{'red' if band == 'Hot' else 'orange' if band == 'Warm' else 'blue'}[{band}]")
        m2.metric("Conversion probability", f"{result['probability']:.0%}")
        m3.metric("Model", f"v{result['model_version']} ({result['variant']})")

        st.subheader("Why this score")
        for r in result["reasons"]:
            arrow = "⬆️" if r["effect"] == "increases" else "⬇️"
            st.write(f"{arrow} **{r['feature'].replace('_', ' ')}** = {r['value']} ({r['effect']} the chance)")

        st.subheader("Suggested follow-up")
        st.write(result["follow_up"]["next_action"])
        if result["follow_up"]["email_opener"]:
            st.info(result["follow_up"]["email_opener"])

        st.caption("After contacting the lead, record the outcome:")
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("✅ Converted"):
            send_feedback(result["prediction_id"], True)
        if b2.button("❌ Lost"):
            send_feedback(result["prediction_id"], False)

# ------------------------------------------------------- lead pipeline quality
with pipeline_tab:
    rows = api("GET", "/predictions", params={"limit": 5000})
    if not rows:
        st.info("No leads scored yet.")
    else:
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["created_at"]).dt.date

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Leads scored", len(df))
        k2.metric("Hot leads", int((df["band"] == "Hot").sum()))
        k3.metric("Average probability", f"{df['probability'].mean():.0%}")
        k4.metric("Leads with feedback", int(df["converted"].notna().sum()))

        st.subheader("Leads per day by band")
        per_day = df.pivot_table(index="date", columns="band", values="id", aggfunc="count").fillna(0)
        st.bar_chart(per_day, color=[BAND_COLORS[b] for b in per_day.columns])

        st.subheader("Average conversion probability per day")
        st.line_chart(df.groupby("date")["probability"].mean())

        st.subheader("Actual conversion rate by band (from rep feedback)")
        labelled = df.dropna(subset=["converted"])
        if len(labelled):
            st.dataframe(labelled.groupby("band")["converted"].agg(leads="count", conversion_rate="mean"))
        else:
            st.caption("No feedback yet.")

        st.subheader("Recent leads")
        st.dataframe(df[["created_at", "band", "probability", "model_version", "variant", "converted"]].head(50),
                     hide_index=True)

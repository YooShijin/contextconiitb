import csv
import io
import json
from collections import Counter

import streamlit as st

from client import CrustError, load
from drafts import write_drafts
from score import inr, parse_need, rank
from step2_companies import fetch_companies
from step3_alumni import fetch_alumni

st.set_page_config(page_title="Alumni Ask", page_icon="🎓", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
.chip {display:inline-block; padding:2px 10px; margin:2px 4px 2px 0; border-radius:999px; font-size:12px; background:rgba(99,102,241,.12);}
.ready {background:#dcfce7; color:#166534;}
.review {background:#fee2e2; color:#991b1b;}
.tag {display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; margin-left:6px;}
</style>
""", unsafe_allow_html=True)

PRESETS = [
    "Techfest needs a title sponsor for its next edition, about ₹50 lakh",
    "The robotics lab needs ₹25 lakh for a new humanoid robot test rig",
    "A scholarship for first generation students in Chemical Engineering, ₹1 crore endowment",
    "The CSE department's AI lab needs ₹2 crore for GPUs",
    "Prize pool for a climate tech hackathon, ₹10 lakh",
]

st.title("Alumni Ask")
st.caption("Tell it what IIT Bombay needs. It finds the alumni who just had a big company milestone and have a real link to that need, explains why, and drafts the ask. A person approves every message.")

companies = load("companies.json") or []
alumni = load("alumni_raw.json") or []

with st.sidebar:
    st.header("Data from Crustdata")
    st.write(f"{len(companies)} companies with money events, {len(alumni)} alumni profiles cached")
    with st.expander("Refresh from Crustdata", expanded=not alumni):
        lookback = st.slider("Money events in the last N days", 30, 365, 180, step=30)
        min_m = st.slider("Smallest round (USD millions)", 1, 100, 5)
        india_only = st.toggle("Indian companies only", value=True)
        if st.button("Pull fresh data", use_container_width=True):
            with st.status("Pulling from Crustdata...", expanded=True) as box:
                try:
                    companies, _ = fetch_companies(lookback, min_m * 1_000_000, "IND" if india_only else None, say=box.write)
                    alumni = fetch_alumni([c["company_id"] for c in companies], say=box.write)
                    box.update(label="Data refreshed", state="complete", expanded=False)
                except (CrustError, ValueError) as err:
                    box.update(label="Crustdata call failed", state="error")
                    st.error(str(err))
    st.header("Settings")
    signer = st.text_input("Signed by", value="Prof. ___, IIT Bombay")
    use_llm = st.toggle("Use Claude for need parsing and drafts", value=True)
    donor_file = st.file_uploader("Existing donors (CSV with a name column)", type=["csv"])

preset = st.selectbox("Start from an example, or write your own below", ["Write my own"] + PRESETS)
need_text = st.text_area("What does IIT Bombay need?", value="" if preset == "Write my own" else preset, height=80)
go = st.button("Find the right alumni", type="primary", disabled=not (need_text.strip() and alumni))

if not alumni:
    st.info("No cached alumni yet. Open 'Refresh from Crustdata' in the sidebar and pull data first.")

if go:
    donors = []
    if donor_file:
        rows = list(csv.reader(io.StringIO(donor_file.getvalue().decode("utf-8", "ignore"))))
        if rows:
            col = next((i for i, h in enumerate(rows[0]) if h.strip().lower() == "name"), 0)
            donors = [r[col] for r in rows[1:] if len(r) > col]
    with st.status("Working...", expanded=True) as box:
        need = parse_need(need_text, use_llm)
        box.write(f"Understood the need ({need['parsed_by']}): departments {need['departments'] or 'any'}, clubs {need['activity_keywords'] or 'none'}, amount {inr(need.get('amount_inr')) or 'not given'}")
        results = rank(alumni, companies, need, donors)
        counts = Counter(r["decision"] for r in results)
        box.write(f"Scored {len(results)} alumni: {dict(counts)}")
        ready = [r for r in results if r["decision"] == "READY"]
        box.write(f"Drafting asks for the top {min(10, len(ready))}")
        write_drafts(ready, need, signer, use_llm)
        box.update(label="Done", state="complete", expanded=False)
    st.session_state["run"] = {"need": need, "results": results}

run = st.session_state.get("run")
if not run:
    st.stop()

need, results = run["need"], run["results"]
groups = {k: [r for r in results if r["decision"] == k] for k in ("READY", "REVIEW", "LATER", "IGNORE")}

chips = "".join(f"<span class='chip'>{d}</span>" for d in need["departments"] + need["activity_keywords"])
st.markdown(f"**Need:** {need['purpose']} {('· ' + inr(need['amount_inr'])) if need.get('amount_inr') else ''}<br>{chips}", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Companies with a money event", len(companies))
m2.metric("Alumni checked", len(results))
m3.metric("Ready to ask", len(groups["READY"]))
m4.metric("Need a human", len(groups["REVIEW"]))


def card(p, i, kind):
    with st.container(border=True):
        label = "READY" if kind == "ready" else "NEEDS HUMAN"
        link = f"[{p['name']}]({p['profile_url']})" if p.get("profile_url") else p["name"]
        st.markdown(f"### {link} <span class='tag {kind}'>{label}</span><span class='tag'>score {p['score']}</span>", unsafe_allow_html=True)
        st.caption(f"{p['title']} at {p['company']} · {p['location'] or ''}")
        st.markdown("**Why this person**")
        for reason in p["reasons"]:
            st.markdown(f"- {reason}")
        for flag in p["flags"]:
            st.warning(flag)
        draft = p.get("draft")
        if draft:
            st.text_input("Subject", draft["subject"], key=f"subj_{kind}_{i}")
            st.text_area("Draft (edit before approving)", draft["body"], key=f"body_{kind}_{i}", height=220)
            st.checkbox("Approve this ask", key=f"ok_{kind}_{i}")
            st.caption(f"Drafted by: {draft['source']}")


st.subheader("Ready to ask")
if not groups["READY"]:
    st.write("Nobody clears the bar for this need. Check 'Better for a different ask' below.")
for i, p in enumerate(groups["READY"][:10]):
    card(p, i, "ready")

if groups["REVIEW"]:
    st.subheader("Escalated to a human")
    st.caption("The agent found a promising alum but something needs checking before anyone reaches out.")
    for i, p in enumerate(groups["REVIEW"]):
        card(p, i, "review")

with st.expander(f"Better for a different ask ({len(groups['LATER'])})"):
    for p in groups["LATER"][:40]:
        st.markdown(f"- **{p['name']}**, {p['title']} at {p['company']} (score {p['score']}): {p['reasons'][-1]}")

with st.expander(f"Ignored, and why ({len(groups['IGNORE'])})"):
    for why, n in Counter(p["why"].split(": ")[-1] for p in groups["IGNORE"]).most_common():
        st.markdown(f"- {n} people: {why}")

approved = []
for i, p in enumerate(groups["READY"][:10]):
    if st.session_state.get(f"ok_ready_{i}"):
        approved.append({"name": p["name"], "profile": p.get("profile_url"), "subject": st.session_state.get(f"subj_ready_{i}"), "body": st.session_state.get(f"body_ready_{i}"), "why": " | ".join(p["reasons"])})

st.divider()
st.write(f"**{len(approved)} asks approved**")
if approved:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(approved[0]))
    writer.writeheader()
    writer.writerows(approved)
    st.download_button("Download approved asks (CSV)", out.getvalue(), file_name="approved_asks.csv", mime="text/csv")
st.download_button("Download full report (JSON)", json.dumps(run, indent=2, default=str), file_name="alumni_report.json", mime="application/json")

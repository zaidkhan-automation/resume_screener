# Resume Screener SaaS — Streamlit MVP (freemium + Razorpay banner)
# ---------------------------------------------------------------
# Run: streamlit run app.py --server.port 8501 --server.address 0.0.0.0
# Env (optional): FREE_LIMIT_PER_DAY=5  DEMO_MAX_MB=5

import os, io, re, json, datetime as dt
from collections import Counter

import streamlit as st
import pandas as pd

# Lightweight parsers
import pdfplumber
import docx2txt

st.set_page_config(page_title="Resume Screener", page_icon="🧾", layout="centered")

# ---------- Config ----------
FREE_LIMIT_PER_DAY = int(os.getenv("FREE_LIMIT_PER_DAY", "5"))
MAX_MB = float(os.getenv("DEMO_MAX_MB", "5"))
PAYMENT_URL = "https://rzp.io/rzp/taskmindai-payment"
CONTACT = "mailto:contact@taskmindai.net"

# ---------- Session guards ----------
if "usage_count" not in st.session_state:
    st.session_state.usage_count = 0
if "last_reset" not in st.session_state:
    st.session_state.last_reset = dt.date.today()
if st.session_state.last_reset != dt.date.today():
    st.session_state.usage_count = 0
    st.session_state.last_reset = dt.date.today()

st.markdown(
    f"""
    <div style="background:#0f1425;border:1px solid #21304d;padding:12px;border-radius:12px;margin:0 0 16px">
      <b>Demo mode:</b> {st.session_state.usage_count} / {FREE_LIMIT_PER_DAY} free screens today.
      <div style="margin-top:6px">
        Want unlimited use + team sharing? <a href="{PAYMENT_URL}" target="_blank" style="color:#9cc9ff">Unlock via Razorpay</a> ·
        <a href="{CONTACT}" style="color:#9cc9ff">Contact</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

def guard_or_stop():
    if st.session_state.usage_count >= FREE_LIMIT_PER_DAY:
        st.error("Daily demo limit reached. Unlock full access to continue.")
        st.link_button("💳 Unlock via Razorpay", PAYMENT_URL, use_container_width=True)
        st.stop()

# ---------- Tiny skill DB (expand later) ----------
SKILL_DB = [
    # Generic
    "python","java","javascript","typescript","c++","c#","sql","nosql","postgresql","mysql","mongodb",
    "excel","power bi","tableau","pandas","numpy","matplotlib","seaborn",
    "fastapi","django","flask","streamlit","react","node","express",
    "aws","gcp","azure","docker","kubernetes","git","linux","bash",
    "nlp","ocr","openai","llm","rag","spaCy","nltk","transformers","pytorch","tensorflow",
    "api","rest","graphql","microservices",
    # Ops/HR/Finance
    "tally","zoho books","quickbooks","payroll","ats","hcm","hrms","excel vlookup","pivot","power query"
]

DEGREE_PAT = r"(b\.?tech|bachelor|be|bsc|msc|mtech|m\.?tech|mba|bca|mca|bcom|mcom|ba|ma)"
EXP_PAT = r"(\d+)\s*(\+?\s*)?(years?|yrs?)"
EMAIL_PAT = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PHONE_PAT = r"(?:\+?\d{1,3}[- ]?)?\d{10}"

def clean_text(t:str)->str:
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    return t

def parse_file(uploaded):
    data = uploaded.read()
    if uploaded.name.lower().endswith(".pdf"):
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:30]:
                text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)
    elif uploaded.name.lower().endswith((".docx",".doc")):
        text = docx2txt.process(io.BytesIO(data))
    elif uploaded.name.lower().endswith((".txt",".md")):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Unsupported file type")
    return text

def extract_contact(text:str):
    emails = re.findall(EMAIL_PAT, text, flags=re.I)
    phones = re.findall(PHONE_PAT, text, flags=re.I)
    return list(dict.fromkeys(emails))[:2], list(dict.fromkeys(phones))[:2]

def extract_skills(text:str):
    txt = clean_text(text)
    found = []
    for s in SKILL_DB:
        # exact or fuzzy-ish contains
        if s in txt:
            found.append(s)
        else:
            # small variants
            s2 = s.replace(" ", "")
            if s2 and s2 in txt.replace(" ",""):
                found.append(s)
    return sorted(list(set(found)))

def extract_years(text:str):
    yrs = [int(m[0]) for m in re.findall(EXP_PAT, text, flags=re.I)]
    return max(yrs) if yrs else None

def score_resume(jd:str, res_text:str):
    jd_clean = clean_text(jd)
    res_clean = clean_text(res_text)

    jd_skills = [s for s in SKILL_DB if s in jd_clean.replace(" ","")]
    res_skills = extract_skills(res_text)
    overlap = sorted(list(set(jd_skills) & set(res_skills)))
    missing = sorted([s for s in jd_skills if s not in res_skills])

    # Basic weights
    skill_score = min(70, len(overlap) * 8)     # up to 70
    exp_res = extract_years(res_text) or 0
    exp_jd = max([int(x) for x in re.findall(r"(\d+)\+?\s*(?:yrs?|years?)", jd_clean)] or [0])
    exp_score = 15 if exp_res >= exp_jd and exp_jd>0 else (8 if exp_res>0 else 0)
    edu_flag = 1 if re.search(DEGREE_PAT, res_text, flags=re.I) else 0
    edu_score = 15 if edu_flag else 5

    total = min(100, skill_score + exp_score + edu_score)

    return {
        "score": int(total),
        "overlap_skills": overlap,
        "missing_skills": missing,
        "resume_years": exp_res,
        "jd_years": exp_jd,
        "has_degree": bool(edu_flag),
    }

# ---------- UI ----------
st.title("🧾 Resume Screener (MVP)")
st.write("Upload a resume and paste a Job Description. The app will extract contacts, detect skills, estimate experience, and give a quick score.")

col1, col2 = st.columns(2)
with col1:
    jd = st.text_area("Job Description (paste)", height=220,
                      placeholder="Paste JD here (required skills, responsibilities, years of experience)…")
with col2:
    file = st.file_uploader("Resume file (PDF/DOCX/TXT)", type=["pdf","docx","doc","txt"],
                            help=f"Max {int(MAX_MB)} MB")

if st.button("🔎 Screen Resume", type="primary", use_container_width=True):
    guard_or_stop()

    if not jd:
        st.error("Please paste the Job Description first.")
        st.stop()
    if not file:
        st.error("Please upload a resume file.")
        st.stop()

    size_mb = file.size / (1024*1024)
    if size_mb > MAX_MB:
        st.error(f"File is {size_mb:.2f} MB. Demo cap is {MAX_MB:.0f} MB.")
        st.stop()

    try:
        text = parse_file(file)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    emails, phones = extract_contact(text)
    skills = extract_skills(text)
    yrs = extract_years(text)
    result = score_resume(jd, text)

    st.success(f"✅ Score: {result['score']}/100")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Matched skills", len(result["overlap_skills"]))
        st.write(", ".join(result["overlap_skills"]) or "—")
    with c2:
        st.metric("Missing skills (from JD)", len(result["missing_skills"]))
        st.write(", ".join(result["missing_skills"]) or "—")

    st.divider()
    st.subheader("Contact & Basics")
    st.write(f"Emails: {', '.join(emails) if emails else '—'}")
    st.write(f"Phones: {', '.join(phones) if phones else '—'}")
    st.write(f"Years of experience (detected): {yrs or '—'}")
    st.write(f"Degree/education mention: {'Yes' if result['has_degree'] else 'Not found'}")

    # Export row
    row = {
        "file": file.name,
        "score": result["score"],
        "resume_years": result["resume_years"],
        "jd_years": result["jd_years"],
        "emails": ";".join(emails),
        "phones": ";".join(phones),
        "skills_matched": ";".join(result["overlap_skills"]),
        "skills_missing": ";".join(result["missing_skills"]),
    }
    df = pd.DataFrame([row])
    st.download_button("📥 Download result (CSV)", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"screener_{file.name}.csv", use_container_width=True)

    st.caption("Demo mode. For unlimited use and ATS export, unlock via Razorpay.")
    st.session_state.usage_count += 1
else:
    st.info("Paste JD and upload a resume to begin.")

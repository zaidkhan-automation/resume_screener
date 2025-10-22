# app.py — Resume Screener (Pure-Python build: pypdf + python-docx)
# Run local:  streamlit run app.py --server.port 8501 --server.address 0.0.0.0

import os, io, re, json, datetime as dt
from typing import List, Tuple

import streamlit as st
import pandas as pd
from pypdf import PdfReader
import docx  # python-docx

# -------------------- Config --------------------
st.set_page_config(page_title="Resume Screener", page_icon="🧾", layout="centered")

FREE_LIMIT_PER_DAY = int(os.getenv("FREE_LIMIT_PER_DAY", "5"))
MAX_MB = float(os.getenv("DEMO_MAX_MB", "5"))
PAYMENT_URL = os.getenv("PAYMENT_URL", "https://rzp.io/rzp/taskmindai-payment")
CONTACT = os.getenv("CONTACT_EMAIL", "mailto:contact@taskmindai.net")

# -------------------- Session guards --------------------
today = dt.date.today()
if "usage_count" not in st.session_state:
    st.session_state.usage_count = 0
if "last_reset" not in st.session_state or st.session_state.last_reset != today:
    st.session_state.last_reset = today
    st.session_state.usage_count = 0

st.markdown(
    f"""
    <div style="background:#0f1425;border:1px solid #21304d;padding:12px;border-radius:12px;margin:0 0 16px">
      <b>Demo mode:</b> {st.session_state.usage_count} / {FREE_LIMIT_PER_DAY} free screens today.
      <div style="margin-top:6px">
        Unlimited use + team export? <a href="{PAYMENT_URL}" target="_blank" style="color:#9cc9ff">Unlock via Razorpay</a> ·
        <a href="{CONTACT}" style="color:#9cc9ff">Contact</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

def stop_if_limit():
    if st.session_state.usage_count >= FREE_LIMIT_PER_DAY:
        st.error("Daily demo limit reached. Unlock full access to continue.")
        st.link_button("💳 Unlock via Razorpay", PAYMENT_URL, use_container_width=True)
        st.stop()

# -------------------- Regex & skills kit --------------------
SKILL_DB = [
    "python","pandas","numpy","fastapi","django","flask","streamlit","sql","postgresql","mysql",
    "mongodb","excel","power bi","tableau","power query","vlookup",
    "aws","gcp","azure","docker","kubernetes","git","linux","bash",
    "nlp","ocr","openai","llm","pytorch","tensorflow",
    "react","node","typescript","javascript",
    "hrms","payroll","tally","ats","api","rest","graphql"
]
DEGREE_PAT = r"(b\.?tech|bachelor|be|bsc|msc|mtech|m\.?tech|mba|bca|mca|bcom|mcom|ba|ma)"
EXP_PAT = r"(\d+)\s*(\+?\s*)?(years?|yrs?)"
EMAIL_PAT = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PHONE_PAT = r"(?:\+?\d{1,3}[- ]?)?\d{10}"

def clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()

# -------------------- File parsers (pure-Python) --------------------
def parse_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for p in reader.pages[:60]:
        txt = p.extract_text() or ""
        parts.append(txt)
    return "\n".join(parts)

def parse_docx(data: bytes) -> str:
    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)

def parse_file(uploaded) -> str:
    data = uploaded.read()
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        return parse_pdf(data)
    elif name.endswith((".docx", ".doc")):
        return parse_docx(data)
    elif name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type")

# -------------------- Extractors --------------------
def extract_contact(text: str) -> Tuple[List[str], List[str]]:
    emails = list(dict.fromkeys(re.findall(EMAIL_PAT, text, flags=re.I)))[:2]
    phones = list(dict.fromkeys(re.findall(PHONE_PAT, text, flags=re.I)))[:2]
    return emails, phones

def extract_skills(text: str) -> List[str]:
    t = clean_text(text)
    t_compact = t.replace(" ", "")
    found = []
    for s in SKILL_DB:
        if s in t or s.replace(" ", "") in t_compact:
            found.append(s)
    return sorted(list(set(found)))

def extract_years(text: str):
    yrs = [int(m[0]) for m in re.findall(EXP_PAT, text, flags=re.I)]
    return max(yrs) if yrs else None

def score_resume(jd: str, resume_text: str):
    jd_clean = clean_text(jd)
    res_skills = extract_skills(resume_text)

    # JD skills filtered from our DB so score stable rahe
    jd_skills = [s for s in SKILL_DB if s in jd_clean.replace(" ", "")]
    overlap = sorted(list(set(jd_skills) & set(res_skills)))
    missing = sorted([s for s in jd_skills if s not in res_skills])

    skill_score = min(70, len(overlap) * 8)
    exp_res = extract_years(resume_text) or 0
    exp_jd = max([int(x) for x in re.findall(r"(\d+)\+?\s*(?:yrs?|years?)", jd_clean)] or [0])
    exp_score = 15 if exp_res >= exp_jd and exp_jd > 0 else (8 if exp_res > 0 else 0)
    edu_score = 15 if re.search(DEGREE_PAT, resume_text, flags=re.I) else 5
    total = min(100, skill_score + exp_score + edu_score)

    return {
        "score": int(total),
        "overlap_skills": overlap,
        "missing_skills": missing,
        "resume_years": exp_res,
        "jd_years": exp_jd,
        "has_degree": bool(re.search(DEGREE_PAT, resume_text, flags=re.I)),
    }

# -------------------- UI --------------------
st.title("🧾 Resume Screener")
st.write("Paste JD, upload resume (PDF/DOCX/TXT). We’ll extract contacts, detect skills, estimate experience, and score the fit.")

c1, c2 = st.columns(2)
with c1:
    jd = st.text_area("Job Description", height=220, placeholder="Required skills + years. Example: Python, Pandas, SQL, 2+ years…")
with c2:
    up = st.file_uploader("Resume file", type=["pdf","docx","doc","txt"], help=f"Max {int(MAX_MB)} MB")

if st.button("🔎 Screen Resume", type="primary", use_container_width=True):
    stop_if_limit()

    if not jd:
        st.error("JD missing. Paste the Job Description.")
        st.stop()
    if not up:
        st.error("Upload a resume file.")
        st.stop()

    size_mb = up.size / (1024 * 1024)
    if size_mb > MAX_MB:
        st.error(f"File is {size_mb:.2f} MB. Demo cap is {MAX_MB:.0f} MB.")
        st.stop()

    try:
        text = parse_file(up)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    res = score_resume(jd, text)
    emails, phones = extract_contact(text)

    st.success(f"✅ Score: {res['score']}/100")
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Matched skills", len(res["overlap_skills"]))
        st.write(", ".join(res["overlap_skills"]) or "—")
    with m2:
        st.metric("Missing skills (from JD)", len(res["missing_skills"]))
        st.write(", ".join(res["missing_skills"]) or "—")

    st.divider()
    st.subheader("Contact & Basics")
    st.write(f"Emails: {', '.join(emails) if emails else '—'}")
    st.write(f"Phones: {', '.join(phones) if phones else '—'}")
    st.write(f"Years of experience (detected): {res['resume_years'] or '—'}")
    st.write(f"Degree mention: {'Yes' if res['has_degree'] else 'Not found'}")

    # CSV export
    row = {
        "file": up.name,
        "score": res["score"],
        "resume_years": res["resume_years"],
        "jd_years": res["jd_years"],
        "emails": ";".join(emails),
        "phones": ";".join(phones),
        "skills_matched": ";".join(res["overlap_skills"]),
        "skills_missing": ";".join(res["missing_skills"]),
    }
    df = pd.DataFrame([row])
    st.download_button(
        "📥 Download result (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"screener_{up.name}.csv",
        use_container_width=True,
    )

    st.caption("Demo mode. For unlimited use and ATS export, unlock via Razorpay.")
    st.session_state.usage_count += 1

else:
    st.info("Paste JD and upload a resume to begin.")

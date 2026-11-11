"""Flask backend - Personal Finance Anomaly Detector."""
import io
import re
import csv
import traceback
from functools import wraps
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from werkzeug.utils import secure_filename
from core import build_trie, categorise, demo_data, detect, rolling_30d, generate_two_month_stories
from s3_storage import upload_file_to_s3, get_last_s3_error, BUCKET_NAME
from charts import (
    generate_monthly_chart,
    generate_category_chart,
    generate_rolling_chart,
    generate_anomaly_chart,
    generate_whatif_chart
)
from db import (
    init_db,
    create_user,
    verify_user_login,
    get_user_by_id,
    save_user_statement,
    get_user_statements,
    get_statement_by_id,
    get_statement_transactions,
    get_user_all_transactions,
    update_statement_analysis
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SECRET_KEY"] = "finlens-secret-key-production-unique"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Initialize SQLite database
init_db()

TRIE = build_trie()
ALLOWED = {"csv", "pdf"}

# Per-user active session cache keyed by user_id
USER_SESSION_STATE = {}


def get_user_state(user_id) -> dict:
    if isinstance(user_id, dict):
        user_id = user_id.get("id")
    if user_id not in USER_SESSION_STATE:
        USER_SESSION_STATE[user_id] = {
            "raw_df": None,
            "source": "none",
            "filename": "",
            "z": 2.5,
            "drift": 4.0
        }
    return USER_SESSION_STATE[user_id]


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required. Please log in."}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"ok": False, "error": "File exceeds maximum size limit of 16MB."}), 413

@app.errorhandler(400)
def bad_request(error):
    msg = getattr(error, 'description', 'Bad Request')
    return jsonify({"ok": False, "error": str(msg)}), 400

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({"ok": False, "error": "Internal server error occurred while processing."}), 500

def allowed(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED

def inr(x):
    try:
        return f"\u20b9{float(x):,.0f}"
    except Exception:
        return "\u20b90"

def clean_amount_val(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return abs(float(val))
    s = str(val).strip()
    s = re.sub(r'[₹$€£\s,]', '', s)
    s = re.sub(r'\((\d+(?:\.\d+)?)\)', r'-\1', s)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:dr|debit)', r'\1', s, flags=re.I)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:cr|credit)', r'-\1', s, flags=re.I)
    try:
        return abs(float(s))
    except Exception:
        return 0.0

def parse_date_robust(val):
    """Robustly parse date strings in ISO (YYYY-MM-DD), DMY (DD/MM/YYYY), and MDY formats."""
    if pd.isna(val) or val is None:
        return pd.NaT
    s = str(val).strip()
    if not s:
        return pd.NaT

    # 1. ISO format: YYYY-MM-DD or YYYY/MM/DD
    m_iso = re.match(r"^(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", s)
    if m_iso:
        try:
            return pd.Timestamp(year=int(m_iso.group(1)), month=int(m_iso.group(2)), day=int(m_iso.group(3)))
        except Exception:
            pass

    # 2. Ambiguous or DMY / MDY format: DD/MM/YYYY or MM/DD/YYYY
    m_dmy = re.match(r"^(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", s)
    if m_dmy:
        p1, p2, yr = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if p1 > 12:  # First part > 12 -> must be Day
            return pd.Timestamp(year=yr, month=p2, day=p1)
        elif p2 > 12:  # Second part > 12 -> must be Day
            return pd.Timestamp(year=yr, month=p1, day=p2)
        else:
            # Default to DD/MM/YYYY for standard bank statements
            return pd.Timestamp(year=yr, month=p2, day=p1)

    return pd.to_datetime(s, errors="coerce")


def parse_csv(b):
    # Try multiple encodings
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin1", "cp1252", "iso-8859-1"):
        try:
            text = b.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        raise ValueError("Could not decode file with supported encodings (UTF-8, Latin1, CP1252).")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Uploaded CSV file is empty.")

    # Locate the header row by searching for date/description/amount keywords
    header_idx = 0
    date_kws = ("date", "txn_date", "trans_date", "value_date", "posting_date", "booking_date", "when", "time")
    desc_kws = ("description", "narration", "particulars", "remarks", "details", "merchant", "payee", "party", "memo", "name")
    amt_kws = ("amount", "debit", "withdrawal", "spend", "expense", "dr", "credit", "deposit")

    for i, line in enumerate(lines[:35]):
        lower_line = line.lower()
        has_date = any(k in lower_line for k in date_kws)
        has_desc = any(k in lower_line for k in desc_kws)
        has_amt = any(k in lower_line for k in amt_kws)
        if (has_date and has_desc) or (has_date and has_amt) or (has_desc and has_amt):
            header_idx = i
            break

    content_from_header = "\n".join(lines[header_idx:])
    try:
        df = pd.read_csv(io.StringIO(content_from_header), sep=None, engine="python")
    except Exception:
        df = pd.read_csv(io.StringIO(content_from_header))

    # Normalize column names
    col_map = {}
    for c in df.columns:
        col_map[c] = re.sub(r'[^a-z0-9]', '_', str(c).strip().lower())
    df.rename(columns=col_map, inplace=True)
    norm_cols = list(df.columns)

    date_col = None
    desc_col = None
    debit_col = None
    credit_col = None
    amt_col = None
    cat_col = None

    for c in norm_cols:
        if not date_col and any(k in c for k in ("date", "txn_date", "trans_date", "value_date", "post")):
            date_col = c
        if not desc_col and any(k in c for k in ("description", "narration", "particular", "remark", "detail", "merchant", "payee", "party", "memo")):
            desc_col = c
        if not debit_col and any(k in c for k in ("debit", "withdrawal", "spend", "dr")):
            debit_col = c
        if not credit_col and any(k in c for k in ("credit", "deposit", "cr")):
            credit_col = c
        if not amt_col and "amount" in c:
            amt_col = c
        if not cat_col and any(k in c for k in ("category", "genre", "tag")):
            cat_col = c

    if not date_col and len(norm_cols) > 0:
        date_col = norm_cols[0]
    if not desc_col:
        for c in norm_cols:
            if c != date_col:
                desc_col = c
                break
    target_amt_col = debit_col or amt_col or (norm_cols[2] if len(norm_cols) > 2 else norm_cols[-1])

    if not date_col or not desc_col or not target_amt_col:
        raise ValueError(f"Could not map columns. Detected: {norm_cols}. CSV requires columns for date, description, and amount.")

    out = pd.DataFrame()
    out["date"] = df[date_col].apply(parse_date_robust)
    out["description"] = df[desc_col].fillna("Unknown Transaction").astype(str)
    out["amount"] = df[target_amt_col].apply(clean_amount_val)
    if cat_col:
        out["category"] = df[cat_col].fillna("").astype(str)
    out = out.dropna(subset=["date"])
    out = out[out["amount"] > 0]

    # Fallback if too few
    if len(out) < 3:
        out = pd.DataFrame()
        out["date"] = df[date_col].apply(parse_date_robust)
        out["description"] = df[desc_col].fillna("Unknown").astype(str)
        out["amount"] = df[target_amt_col].apply(clean_amount_val)
        if cat_col:
            out["category"] = df[cat_col].fillna("").astype(str)
        out = out.dropna(subset=["date"])

    if len(out) < 3:
        raise ValueError(f"Could only find {len(out)} valid transactions. Please ensure your file has date, description, and positive amount entries.")

    out["date"] = out["date"].dt.normalize()
    return out.sort_values("date").reset_index(drop=True)

def parse_pdf(b):
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is not installed. Please install pdfplumber.")
    rows = []
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for pg in pdf.pages:
            tables = pg.extract_tables() or []
            for t in tables:
                if t:
                    for row in t:
                        if row and any(cell for cell in row):
                            clean_row = [str(c).strip() if c is not None else "" for c in row]
                            if len(clean_row) >= 3:
                                rows.append(clean_row)
    if not rows:
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            text_lines = []
            for pg in pdf.pages:
                txt = pg.extract_text()
                if txt:
                    text_lines.extend(txt.splitlines())
            date_regex = re.compile(r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{2,4})')
            amt_regex = re.compile(r'([\d,]+\.\d{2})')
            parsed_rows = []
            for line in text_lines:
                dm = date_regex.search(line)
                am = amt_regex.findall(line)
                if dm and am:
                    d_str = dm.group(1)
                    a_str = am[-1]
                    desc_str = line.replace(d_str, "").replace(a_str, "").strip()
                    parsed_rows.append([d_str, desc_str, a_str])
            if parsed_rows:
                rows = [["Date", "Description", "Amount"]] + parsed_rows

    if not rows or len(rows) < 4:
        raise ValueError("Could not extract transaction tables from PDF. Please export your statement as a CSV file.")

    sio = io.StringIO()
    writer = csv.writer(sio)
    for r in rows:
        writer.writerow(r)
    return parse_csv(sio.getvalue().encode("utf-8"))

def analyse(raw, z=2.5, dp=4.0, user_id=None):
    raw = raw.copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    df = categorise(raw, TRIE)
    events, subs, monthly = detect(df, z, dp)
    r30 = rolling_30d(df)
    total = float(df["amount"].sum())
    leak = sum(e["yearly"] for e in events if e["kind"] in ("creep", "new", "drift"))
    score = min(100, int(leak / max(total, 1) * 600))
    act = subs[subs["active"]] if len(subs) else pd.DataFrame()
    sm = float(act["amount"].sum()) if len(act) else 0.0
    cats = df[df["amount"] > 0].groupby("category")["amount"].sum().sort_values(ascending=False)
    cat_d = [{"category": c, "total": round(float(a), 2), "pct": round(100 * float(a) / max(total, 1), 1)} for c, a in cats.items() if a > 0]

    # Dynamically group expense transactions by month from actual transaction dates
    expense_df = df[df["amount"] > 0].copy()
    if len(expense_df) > 0:
        expense_df["month_key"] = expense_df["date"].dt.to_period("M")
        monthly_spend = expense_df.groupby("month_key")["amount"].sum().sort_index()
        # Only include months that actually have transaction data (no zeros, no artificial resampling)
        mt_d = [{"month": str(p), "total": round(float(amt), 2)} for p, amt in monthly_spend.items() if amt > 0]
    else:
        mt_d = []

    daily_s = df[df["amount"] > 0].groupby(df["date"].dt.strftime("%Y-%m-%d"))["amount"].sum()
    daily_d = [{"date": d, "amount": round(float(a), 2)} for d, a in daily_s.items()]
    rd = [{"date": str(i)[:10], "amount": round(float(v), 2)} for i, v in r30.items()]
    ICON = {"creep": "🔺", "new": "🆕", "dup": "👯", "drift": "📈", "spike": "⚡"}
    SL = {1: "Worth a look", 2: "Notable", 3: "Important"}
    ev_d = [{
        "date": str(e["date"])[:10],
        "month": "{:%B %Y}".format(e["date"]),
        "kind": e["kind"],
        "icon": ICON.get(e["kind"], "ℹ"),
        "severity": e["severity"],
        "sev_label": SL.get(e["severity"], ""),
        "title": e["title"],
        "why": e["why"],
        "series": e["series"] or [],
        "yearly": round(float(e["yearly"]), 2),
        "merchant": e["merchant"] or "",
    } for e in events]
    subs_d = [{
        "merchant": s["merchant"],
        "category": s["category"],
        "first": str(s["first"])[:10],
        "last": str(s["last"])[:10],
        "first_amount": round(float(s["first_amount"]), 2),
        "amount": round(float(s["amount"]), 2),
        "active": bool(s["active"]),
        "charges": int(s["charges"]),
        "yearly": round(float(s["amount"]) * 12, 2),
    } for _, s in subs.iterrows()]
    top = df.nlargest(10, "amount")[["date", "merchant", "category", "amount"]].copy()
    top["date"] = top["date"].astype(str).str[:10]
    anom = [e for e in ev_d if e["kind"] in ("dup", "spike", "creep", "new", "drift")]
    # Generate dashboard graphs using Python
    m = list(range(13))
    keep = [round(sm * k, 2) for k in m]
    chart_urls = {
        "monthly": generate_monthly_chart(mt_d, daily_data=daily_d, user_id=user_id),
        "category": generate_category_chart(cat_d, user_id=user_id),
        "rolling": generate_rolling_chart(rd, user_id=user_id),
        "anomalies": generate_anomaly_chart(ev_d, user_id=user_id),
        "whatif": generate_whatif_chart(m, keep, keep, user_id=user_id)
    }

    ds = df.sort_values("date", ascending=False).head(50)
    all_tx = [{"date": str(r["date"])[:10], "description": r["description"], "merchant": r["merchant"], "category": r["category"], "amount": round(float(r["amount"]), 2)} for _, r in ds.iterrows()]
    return {
        "summary": {
            "total_spend": round(total, 2), "total_spend_fmt": inr(total),
            "leak_year": round(leak, 2), "leak_year_fmt": inr(leak),
            "leak_score": score,
            "sub_monthly": round(sm, 2), "sub_monthly_fmt": inr(sm), "sub_yearly_fmt": inr(sm * 12),
            "alert_count": len(events), "tx_count": len(df),
            "date_from": str(df["date"].min())[:10], "date_to": str(df["date"].max())[:10],
            "active_sub_count": len(act),
        },
        "category_data": cat_d, "monthly_trend": mt_d, "rolling_data": rd,
        "events": ev_d, "anomalies": anom, "subscriptions": subs_d,
        "charts": chart_urls,
        "top_transactions": top.to_dict(orient="records"), "all_transactions": all_tx,
        "z": z, "drift": dp
    }

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("login.html", error="Email and password are required.", email=email)

        user = verify_user_login(email, password)
        if not user:
            return render_template("login.html", error="Invalid email address or password.", email=email)

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            return render_template("signup.html", error="All fields are required.", name=name, email=email)

        if password != confirm_password:
            return render_template("signup.html", error="Passwords do not match.", name=name, email=email)

        if len(password) < 6:
            return render_template("signup.html", error="Password must be at least 6 characters long.", name=name, email=email)

        try:
            user = create_user(name, email, password)
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            return redirect(url_for("index"))
        except ValueError as ex:
            return render_template("signup.html", error=str(ex), name=name, email=email)

    return render_template("signup.html")


@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    user = get_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"ok": False, "error": "User session expired or not found."}), 401
    return jsonify({"ok": True, "user": user})


@app.route("/api/demo")
@login_required
def api_demo():
    try:
        user_id = session["user_id"]
        z = float(request.args.get("z", 2.5))
        dp = float(request.args.get("drift", 4.0))
        raw = demo_data()
        raw_cat = categorise(raw.copy(), TRIE)

        user_state = get_user_state(user_id)
        user_state["raw_df"] = raw.copy()
        user_state["source"] = "demo"
        user_state["filename"] = "demo_data.csv"
        user_state["z"] = z
        user_state["drift"] = dp

        r = analyse(raw, z, dp, user_id=f"demo_{user_id}")
        r["source"] = "demo"
        r["filename"] = "demo_data.csv"
        r["stories_two_months"] = generate_two_month_stories(raw_cat)
        return jsonify({"ok": True, "data": r})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    try:
        user_id = session["user_id"]

        if "file" not in request.files:
            return jsonify({
                "ok": False,
                "error": "No file included in upload request."
            }), 400

        f = request.files["file"]

        if not f or not f.filename:
            return jsonify({
                "ok": False,
                "error": "No file selected."
            }), 400

        if not allowed(f.filename):
            return jsonify({
                "ok": False,
                "error": "Unsupported file format. Please upload a CSV or PDF file."
            }), 400

        # Read uploaded file
        b = f.read()

        if not b:
            return jsonify({
                "ok": False,
                "error": "The uploaded file is empty (0 bytes)."
            }), 400

        import os
        import uuid

        ext = f.filename.rsplit(".", 1)[1].lower()
        safe_name = secure_filename(f.filename)

        # Upload original file to AWS S3 in uploads/ folder
        s3_filename = f"uploads/{uuid.uuid4().hex}_{safe_name}"

        temp_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"temp_{uuid.uuid4().hex}_{safe_name}"
        )

        s3_key = s3_filename
        try:
            with open(temp_path, "wb") as temp_file:
                temp_file.write(b)

            s3_uploaded = upload_file_to_s3(
                temp_path,
                s3_filename
            )

            if s3_uploaded:
                s3_key = s3_filename
                print(f"[AWS S3] Upload successful and verified in bucket '{BUCKET_NAME}': {s3_filename}")
            else:
                err_msg = get_last_s3_error() or "S3 upload not completed."
                print(f"[AWS S3 Notice] Could not complete S3 upload ({BUCKET_NAME}): {err_msg}. Continuing with local analysis.")
                s3_key = f"uploads/{safe_name}"

        except Exception as s3_ex:
            print(f"[AWS S3 Notice] S3 upload exception: {s3_ex}. Continuing with local analysis.")
            s3_key = f"uploads/{safe_name}"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # Parse the uploaded file
        raw = parse_csv(b) if ext == "csv" else parse_pdf(b)

        if len(raw) < 3:
            return jsonify({
                "ok": False,
                "error": (
                    f"Only found {len(raw)} valid transactions. "
                    "Please upload a statement with at least 3 transactions."
                )
            }), 400

        # Read analysis settings
        z = float(request.form.get("z", 2.5))
        dp = float(request.form.get("drift", 4.0))

        # Categorise transactions for clean merchant and category storage
        raw_norm = raw.copy()
        raw_norm["date"] = pd.to_datetime(raw_norm["date"]).dt.normalize()
        df_cat = categorise(raw_norm, TRIE)

        # Analyse transactions
        r = analyse(raw, z, dp, user_id=user_id)
        r["source"] = "upload"
        r["filename"] = safe_name
        r["s3_key"] = s3_key

        # Persist statement and individual transactions in SQLite linked to this user
        stmt_id = save_user_statement(user_id, safe_name, safe_name, s3_key, df_cat, r)
        r["statement_id"] = stmt_id

        # Update in-memory session cache for this user
        user_state = get_user_state(user_id)
        user_state["raw_df"] = raw.copy()
        user_state["source"] = "upload"
        user_state["filename"] = safe_name
        user_state["statement_id"] = stmt_id
        user_state["z"] = z
        user_state["drift"] = dp
        session["active_statement_id"] = stmt_id

        # Generate financial stories using user's transactions
        all_user_txs = get_user_all_transactions(user_id)
        if all_user_txs:
            r["stories_two_months"] = generate_two_month_stories(pd.DataFrame(all_user_txs))
        else:
            r["stories_two_months"] = generate_two_month_stories(raw)

        return jsonify({
            "ok": True,
            "data": r
        })

    except ValueError as ex:
        return jsonify({
            "ok": False,
            "error": str(ex)
        }), 400

    except Exception as ex:
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": "Analysis failed: " + str(ex)
        }), 500


@app.route("/api/history", methods=["GET"])
@login_required
def api_history():
    try:
        user_id = session["user_id"]
        statements = get_user_statements(user_id)
        return jsonify({"ok": True, "statements": statements})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/history/<int:statement_id>", methods=["GET"])
@login_required
def api_history_detail(statement_id):
    try:
        user_id = session["user_id"]
        statement = get_statement_by_id(statement_id, user_id)
        if not statement:
            return jsonify({"ok": False, "error": "Statement not found or unauthorized access."}), 404

        txs = get_statement_transactions(statement_id, user_id)
        return jsonify({
            "ok": True,
            "statement": {
                "id": statement["id"],
                "filename": statement["filename"],
                "upload_date": statement["upload_date"],
                "tx_count": statement["tx_count"],
                "total_spend": statement["total_spend"],
                "date_from": statement["date_from"],
                "date_to": statement["date_to"],
                "status": statement["status"]
            },
            "transactions": txs
        })
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/history/<int:statement_id>/load", methods=["POST"])
@login_required
def api_history_load(statement_id):
    try:
        user_id = session["user_id"]
        statement = get_statement_by_id(statement_id, user_id)
        if not statement:
            return jsonify({"ok": False, "error": "Statement not found or unauthorized access."}), 404

        txs = get_statement_transactions(statement_id, user_id)
        if txs:
            raw_df = pd.DataFrame(txs)
            raw_df["date"] = pd.to_datetime(raw_df["date"])
        else:
            raw_df = pd.DataFrame()

        user_state = get_user_state(user_id)
        user_state["raw_df"] = raw_df
        user_state["source"] = "history"
        user_state["filename"] = statement["filename"]

        if len(raw_df) > 0:
            analysis = analyse(raw_df, user_state.get("z", 2.5), user_state.get("drift", 4.0), user_id=user_id)
            update_statement_analysis(statement_id, user_id, analysis)
        else:
            analysis = statement.get("analysis") or {}

        if analysis:
            analysis["source"] = "history"
            analysis["filename"] = statement["filename"]
            # Attach 2-month stories
            all_user_txs = get_user_all_transactions(user_id)
            if all_user_txs:
                analysis["stories_two_months"] = generate_two_month_stories(pd.DataFrame(all_user_txs))
            elif len(raw_df) > 0:
                analysis["stories_two_months"] = generate_two_month_stories(raw_df)

        return jsonify({"ok": True, "data": analysis})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/stories", methods=["GET"])
@login_required
def api_stories():
    try:
        user_id = session["user_id"]
        txs = get_user_all_transactions(user_id)
        if not txs:
            user_state = get_user_state(user_id)
            raw = user_state.get("raw_df")
            if raw is not None and len(raw) > 0:
                stories = generate_two_month_stories(raw)
                return jsonify({"ok": True, "data": stories})
            return jsonify({
                "ok": True,
                "data": {
                    "has_enough_data": False,
                    "message": "No transaction history available for your account. Upload a bank statement to generate Financial Stories.",
                    "stories": []
                }
            })

        df = pd.DataFrame(txs)
        stories = generate_two_month_stories(df)
        return jsonify({"ok": True, "data": stories})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/analyse", methods=["GET", "POST"])
@login_required
def api_analyse():
    """Return the currently active statement analysis for the logged-in user.
    Uses the active uploaded data if available, or the latest uploaded statement
    from database, falling back to demo data only if the user has no statements."""
    try:
        user_id = session["user_id"]
        user_state = get_user_state(user_id)
        raw = user_state.get("raw_df")

        # 1. Active in-memory uploaded statement
        if raw is not None and len(raw) > 0 and user_state.get("source") != "demo":
            body = request.get_json(silent=True) or {}
            z = float(request.args.get("z") or body.get("z") or user_state.get("z", 2.5))
            dp = float(request.args.get("drift") or body.get("drift") or user_state.get("drift", 4.0))
            r = analyse(raw, z, dp, user_id=user_id)
            r["source"] = "upload"
            r["filename"] = user_state.get("filename", "statement.csv")
            return jsonify({"ok": True, "data": r})

        # 2. Check if user has uploaded statements in database
        stmts = get_user_statements(user_id)
        if stmts and len(stmts) > 0:
            latest_stmt = stmts[0]
            txs = get_statement_transactions(latest_stmt["id"], user_id)
            if txs:
                df = pd.DataFrame(txs)
                df["date"] = pd.to_datetime(df["date"])
                user_state["raw_df"] = df.copy()
                user_state["source"] = "history"
                user_state["filename"] = latest_stmt["filename"]
                user_state["statement_id"] = latest_stmt["id"]
                r = analyse(df, user_state.get("z", 2.5), user_state.get("drift", 4.0), user_id=user_id)
                r["source"] = "history"
                r["filename"] = latest_stmt["filename"]
                return jsonify({"ok": True, "data": r})

        # 3. Fallback to demo data only if user has zero statements
        raw = demo_data()
        user_state["raw_df"] = raw.copy()
        user_state["source"] = "demo"
        user_state["filename"] = "demo_data.csv"
        r = analyse(raw, user_state.get("z", 2.5), user_state.get("drift", 4.0), user_id=f"demo_{user_id}")
        r["source"] = "demo"
        r["filename"] = "demo_data.csv"
        return jsonify({"ok": True, "data": r})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


@app.route("/api/reanalyse", methods=["GET", "POST"])
@login_required
def api_reanalyse():
    try:
        user_id = session["user_id"]
        user_state = get_user_state(user_id)
        raw = user_state.get("raw_df")

        if raw is None or len(raw) == 0:
            txs = get_user_all_transactions(user_id)
            if txs:
                raw = pd.DataFrame(txs)
                raw["date"] = pd.to_datetime(raw["date"])
            else:
                raw = demo_data()
                user_state["source"] = "demo"
                user_state["filename"] = "demo_data.csv"
            user_state["raw_df"] = raw.copy()
        else:
            raw = raw.copy()

        body = request.get_json(silent=True) or {}
        z_str = request.args.get("z") or request.form.get("z") or body.get("z") or user_state.get("z", 2.5)
        dp_str = request.args.get("drift") or request.form.get("drift") or body.get("drift") or user_state.get("drift", 4.0)

        z = float(z_str)
        dp = float(dp_str)
        user_state["z"] = z
        user_state["drift"] = dp

        # Perform a completely fresh analysis on original raw transactions with new thresholds
        r = analyse(raw, z, dp, user_id=user_id)
        r["source"] = user_state.get("source", "upload")
        r["filename"] = user_state.get("filename", "")
        r["z"] = z
        r["drift"] = dp

        all_user_txs = get_user_all_transactions(user_id)
        if all_user_txs:
            r["stories_two_months"] = generate_two_month_stories(pd.DataFrame(all_user_txs))
        else:
            r["stories_two_months"] = generate_two_month_stories(raw)

        return jsonify({"ok": True, "data": r})
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": f"Re-analysis failed: {str(ex)}"}), 500


@app.route("/api/whatif", methods=["POST"])
@login_required
def api_whatif():
    try:
        body = request.get_json(force=True, silent=True) or {}
        subs = body.get("subscriptions", [])
        cancel = set(body.get("cancel", []))

        tot = sum(float(s.get("amount", 0)) for s in subs if s.get("active"))
        sav = sum(
            float(s.get("amount", 0)) for s in subs
            if s.get("active") and s.get("merchant") in cancel
        )

        m = list(range(13))

        keep = [round(tot * k, 2) for k in m]
        after = [round((tot - sav) * k, 2) for k in m]

        user_id = session.get("user_id")
        chart_url = generate_whatif_chart(m, keep, after, user_id=user_id)

        return jsonify({
            "ok": True,
            "total_monthly": round(tot, 2),
            "saved_monthly": round(sav, 2),
            "saved_yearly": round(sav * 12, 2),
            "new_monthly": round(tot - sav, 2),
            "chart_url": chart_url
        })

    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(ex)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sqlite3
import os
import shutil
import uuid
from datetime import datetime, date
from typing import Optional
import json

app = FastAPI(title="Utility Choice Tracker")

STATIC_DIR = "/app/static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/data/utility.db"
UPLOADS_PATH = "/uploads"
os.makedirs(UPLOADS_PATH, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ── Database init + migration ─────────────────────────────────────────────────

def init_db():
    conn = get_db()
    c = conn.cursor()

    # ── v1.0 tables (always safe to run) ──────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # ── v1.1 migration: addresses table ───────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            street TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            cc_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check if suppliers table exists and whether it already has address_id
    tables = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    if "suppliers" not in tables:
        # Fresh install — create with address_id from the start
        c.execute("""
            CREATE TABLE suppliers (
                id TEXT PRIMARY KEY,
                address_id TEXT NOT NULL,
                utility_type TEXT NOT NULL,
                supplier_name TEXT NOT NULL,
                rate REAL NOT NULL,
                rate_unit TEXT NOT NULL,
                term_start DATE NOT NULL,
                term_end DATE NOT NULL,
                account_number TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (address_id) REFERENCES addresses(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                supplier_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        """)
    else:
        # Existing install — check if migration needed
        cols = [r[1] for r in c.execute("PRAGMA table_info(suppliers)").fetchall()]
        if "address_id" not in cols:
            # ── Migrate from v1.0 to v1.1 ─────────────────────────────────────
            print("Migrating database from v1.0 to v1.1...")

            # 1. Create a default address for all existing data
            default_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO addresses (id, name) VALUES (?, ?)",
                (default_id, "Default")
            )

            # 2. Add address_id column (nullable for now to allow migration)
            c.execute("ALTER TABLE suppliers ADD COLUMN address_id TEXT")

            # 3. Assign all existing suppliers to the default address
            c.execute(
                "UPDATE suppliers SET address_id = ?",
                (default_id,)
            )

            print(f"Migration complete. Existing suppliers assigned to address '{default_id}'.")

        # Ensure documents table exists (may be missing on very early installs)
        c.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                supplier_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        """)

    # ── v1.1.1 migration: cc_email on addresses ────────────────────────────────
    addr_cols = [r[1] for r in c.execute("PRAGMA table_info(addresses)").fetchall()]
    if "cc_email" not in addr_cols:
        print("Migrating addresses table: adding cc_email column...")
        c.execute("ALTER TABLE addresses ADD COLUMN cc_email TEXT")

    # ── Default settings ───────────────────────────────────────────────────────
    defaults = [
        ("smtp_host", ""),
        ("smtp_port", "587"),
        ("smtp_user", ""),
        ("smtp_password", ""),
        ("smtp_from", ""),
        ("alert_email", ""),
        ("alert_days", json.dumps([30, 60, 90])),
        ("smtp_tls", "true"),
        ("compare_url", "https://www.energychoice.ohio.gov/ApplestoApples.aspx"),
    ]
    for key, value in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()
    conn.close()

init_db()

# ── Addresses ─────────────────────────────────────────────────────────────────

@app.get("/api/addresses")
def list_addresses():
    conn = get_db()
    rows = conn.execute("SELECT * FROM addresses ORDER BY created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/addresses")
def create_address(data: dict):
    address_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO addresses (id, name, street, city, state, zip, cc_email) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (address_id, data.get("name", "New Address"),
         data.get("street", ""), data.get("city", ""),
         data.get("state", ""), data.get("zip", ""),
         data.get("cc_email", ""))
    )
    conn.commit()
    conn.close()
    return {"id": address_id}

@app.put("/api/addresses/{address_id}")
def update_address(address_id: str, data: dict):
    conn = get_db()
    row = conn.execute("SELECT id FROM addresses WHERE id = ?", (address_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Address not found")
    conn.execute(
        "UPDATE addresses SET name=?, street=?, city=?, state=?, zip=?, cc_email=? WHERE id=?",
        (data.get("name", ""), data.get("street", ""),
         data.get("city", ""), data.get("state", ""),
         data.get("zip", ""), data.get("cc_email", ""), address_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/addresses/{address_id}")
def delete_address(address_id: str):
    conn = get_db()
    # Check address exists
    row = conn.execute("SELECT id FROM addresses WHERE id = ?", (address_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Address not found")
    # Prevent deleting the last address
    count = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
    if count <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot delete the last address.")
    # Delete all suppliers (and their documents) for this address
    suppliers = conn.execute(
        "SELECT id FROM suppliers WHERE address_id = ?", (address_id,)
    ).fetchall()
    for s in suppliers:
        docs = conn.execute(
            "SELECT filename FROM documents WHERE supplier_id = ?", (s["id"],)
        ).fetchall()
        for d in docs:
            fpath = os.path.join(UPLOADS_PATH, d["filename"])
            if os.path.exists(fpath):
                os.remove(fpath)
        conn.execute("DELETE FROM documents WHERE supplier_id = ?", (s["id"],))
    conn.execute("DELETE FROM suppliers WHERE address_id = ?", (address_id,))
    conn.execute("DELETE FROM addresses WHERE id = ?", (address_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Suppliers ─────────────────────────────────────────────────────────────────

def _enrich(s: dict, today: date) -> dict:
    end = date.fromisoformat(s["term_end"])
    start = date.fromisoformat(s["term_start"])
    days_left = (end - today).days
    total_days = (end - start).days or 1
    elapsed = (today - start).days
    s["days_remaining"] = days_left
    s["progress"] = max(0, min(100, int(elapsed / total_days * 100)))
    if days_left < 0:
        s["status"] = "expired"
    elif days_left <= 30:
        s["status"] = "critical"
    elif days_left <= 90:
        s["status"] = "warning"
    else:
        s["status"] = "active"
    return s

@app.get("/api/addresses/{address_id}/suppliers")
def list_suppliers(address_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE address_id = ? ORDER BY term_end ASC",
        (address_id,)
    ).fetchall()
    conn.close()
    today = date.today()
    return [_enrich(dict(r), today) for r in rows]

@app.get("/api/suppliers/{supplier_id}")
def get_supplier(supplier_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return dict(row)

@app.post("/api/addresses/{address_id}/suppliers")
def create_supplier(
    address_id: str,
    utility_type: str = Form(...),
    supplier_name: str = Form(...),
    rate: float = Form(...),
    rate_unit: str = Form(...),
    term_start: str = Form(...),
    term_end: str = Form(...),
    account_number: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    conn = get_db()
    row = conn.execute("SELECT id FROM addresses WHERE id = ?", (address_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Address not found")
    supplier_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO suppliers (id, address_id, utility_type, supplier_name, rate, rate_unit,
           term_start, term_end, account_number, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (supplier_id, address_id, utility_type, supplier_name, rate, rate_unit,
         term_start, term_end, account_number, notes)
    )
    for f in files:
        if f.filename:
            _save_file(conn, supplier_id, f)
    conn.commit()
    conn.close()
    return {"id": supplier_id}

@app.put("/api/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: str,
    utility_type: str = Form(...),
    supplier_name: str = Form(...),
    rate: float = Form(...),
    rate_unit: str = Form(...),
    term_start: str = Form(...),
    term_end: str = Form(...),
    account_number: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    conn = get_db()
    row = conn.execute("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Supplier not found")
    conn.execute(
        """UPDATE suppliers SET utility_type=?, supplier_name=?, rate=?, rate_unit=?,
           term_start=?, term_end=?, account_number=?, notes=? WHERE id=?""",
        (utility_type, supplier_name, rate, rate_unit,
         term_start, term_end, account_number, notes, supplier_id)
    )
    for f in files:
        if f.filename:
            _save_file(conn, supplier_id, f)
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str):
    conn = get_db()
    docs = conn.execute(
        "SELECT filename FROM documents WHERE supplier_id = ?", (supplier_id,)
    ).fetchall()
    for d in docs:
        fpath = os.path.join(UPLOADS_PATH, d["filename"])
        if os.path.exists(fpath):
            os.remove(fpath)
    conn.execute("DELETE FROM documents WHERE supplier_id = ?", (supplier_id,))
    conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Documents ─────────────────────────────────────────────────────────────────

def _save_file(conn, supplier_id: str, f: UploadFile):
    ext = os.path.splitext(f.filename)[1]
    stored_name = str(uuid.uuid4()) + ext
    dest = os.path.join(UPLOADS_PATH, stored_name)
    with open(dest, "wb") as out:
        shutil.copyfileobj(f.file, out)
    doc_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO documents (id, supplier_id, filename, original_filename) VALUES (?, ?, ?, ?)",
        (doc_id, supplier_id, stored_name, f.filename)
    )

@app.get("/api/suppliers/{supplier_id}/documents")
def list_documents(supplier_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM documents WHERE supplier_id = ?", (supplier_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    fpath = os.path.join(UPLOADS_PATH, row["filename"])
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(fpath, filename=row["original_filename"])

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")
    fpath = os.path.join(UPLOADS_PATH, row["filename"])
    if os.path.exists(fpath):
        os.remove(fpath)
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    d = {r["key"]: r["value"] for r in rows}
    if d.get("smtp_password"):
        d["smtp_password_set"] = True
        d["smtp_password"] = ""
    return d

@app.post("/api/settings")
def save_settings(data: dict):
    conn = get_db()
    for key, value in data.items():
        if key == "smtp_password" and value == "":
            continue
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value) if not isinstance(value, str) else value)
        )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/settings/test-email")
def test_email():
    result = _send_email(
        subject="Utility Choice Tracker — Test Email",
        body="Your email settings are configured correctly! You will receive contract expiration alerts at this address."
    )
    if result:
        return {"ok": True}
    raise HTTPException(status_code=500, detail="Failed to send email. Check your SMTP settings.")

# ── Email / Scheduler ─────────────────────────────────────────────────────────

def _get_setting(key: str) -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""

def _send_email(subject: str, body: str, cc: str = "") -> bool:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        host         = _get_setting("smtp_host")
        port         = int(_get_setting("smtp_port") or 587)
        user         = _get_setting("smtp_user")
        password_enc = _get_setting("smtp_password")
        from_addr    = _get_setting("smtp_from") or user
        to_addr      = _get_setting("alert_email")
        use_tls      = _get_setting("smtp_tls") == "true"
        if not all([host, user, password_enc, to_addr]):
            return False
        import base64
        password = base64.b64decode(password_enc).decode()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "html"))
        recipients = [to_addr] + [c.strip() for c in cc.split(",") if c.strip()]
        with smtplib.SMTP(host, port) as s:
            if use_tls:
                s.starttls()
            s.login(user, password)
            s.sendmail(from_addr, recipients, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

@app.post("/api/check-alerts")
def check_alerts(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_alert_check)
    return {"ok": True, "message": "Alert check queued"}

def _run_alert_check():
    conn = get_db()
    # Join to get address name for richer alert emails
    suppliers = conn.execute("""
        SELECT s.*, a.name as address_name, a.street, a.city, a.state, a.zip, a.cc_email as address_cc_email
        FROM suppliers s
        JOIN addresses a ON s.address_id = a.id
    """).fetchall()
    conn.close()
    alert_days_raw = _get_setting("alert_days")
    try:
        alert_days = json.loads(alert_days_raw)
    except:
        alert_days = [30, 60, 90]
    today = date.today()
    for s in suppliers:
        end = date.fromisoformat(s["term_end"])
        days_left = (end - today).days
        for threshold in alert_days:
            if days_left == threshold:
                _send_expiration_alert(dict(s), days_left)
                break

def _send_expiration_alert(supplier: dict, days_left: int):
    utility_emoji = "⚡" if supplier["utility_type"] == "electric" else "🔥"
    address_label = supplier.get("address_name", "")
    # Build a readable address line if details exist
    parts = [supplier.get("street",""), supplier.get("city",""),
             supplier.get("state",""), supplier.get("zip","")]
    address_line = ", ".join(p for p in parts if p) or address_label
    compare_url  = _get_setting("compare_url") or "https://www.energychoice.ohio.gov/ApplestoApples.aspx"

    subject = f"{utility_emoji} Action Required: {supplier['supplier_name']} contract expires in {days_left} days"
    body = f"""
    <html><body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1a1a2e;">
    <div style="border-left: 4px solid #e63946; padding-left: 20px; margin-bottom: 30px;">
        <h1 style="color: #e63946; margin: 0 0 8px 0;">Utility Contract Expiring Soon</h1>
        <p style="color: #666; margin: 0;">Energy Choice Reminder</p>
    </div>
    <p>Your <strong>{supplier['utility_type'].title()}</strong> supplier contract with
    <strong>{supplier['supplier_name']}</strong> expires in
    <strong style="color: #e63946;">{days_left} days</strong> on
    <strong>{supplier['term_end']}</strong>.</p>
    <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <p style="margin: 4px 0;"><strong>Address:</strong> {address_line}</p>
        <p style="margin: 4px 0;"><strong>Current Rate:</strong> {supplier['rate']} / {supplier['rate_unit']}</p>
        <p style="margin: 4px 0;"><strong>Account:</strong> {supplier.get('account_number') or 'N/A'}</p>
    </div>
    <p>⚠️ <strong>After your contract expires, you may be moved to a variable rate that can increase significantly.</strong></p>
    <p>Check your state's energy choice website to compare suppliers and choose a new plan before your contract ends.</p>
    <a href="{compare_url}"
       style="display: inline-block; background: #1a1a2e; color: white; padding: 12px 24px;
              border-radius: 6px; text-decoration: none; font-weight: bold; margin: 10px 0;">
        Compare Energy Suppliers →
    </a>
    <p style="color: #999; font-size: 12px; margin-top: 30px;">Sent by Utility Choice Tracker</p>
    </body></html>
    """
    cc_email     = supplier.get("address_cc_email", "") or ""
    _send_email(subject, body, cc=cc_email)

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/api/addresses/{address_id}/dashboard")
def dashboard(address_id: str):
    conn = get_db()
    row = conn.execute("SELECT id FROM addresses WHERE id = ?", (address_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Address not found")
    suppliers = conn.execute(
        "SELECT * FROM suppliers WHERE address_id = ? ORDER BY term_end ASC",
        (address_id,)
    ).fetchall()
    conn.close()
    today = date.today()

    all_enriched = [_enrich(dict(s), today) for s in suppliers]

    def panel_for(utility_type):
        contracts   = [s for s in all_enriched if s["utility_type"] == utility_type]
        non_expired = [s for s in contracts if s["status"] != "expired"]
        current     = non_expired[0] if non_expired else None
        upcoming    = non_expired[1] if len(non_expired) > 1 else None
        expired_list = [s for s in contracts if s["status"] == "expired"]
        return {
            "current":       current,
            "upcoming":      upcoming,
            "expired_count": len(expired_list),
        }

    return {
        "electric": panel_for("electric"),
        "gas":      panel_for("gas"),
    }

# ── Serve frontend ────────────────────────────────────────────────────────────

if os.path.isdir(STATIC_DIR) and os.listdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=FileResponse)
    def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

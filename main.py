from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import hashlib
import secrets
from datetime import datetime
import os  # Env o'zgaruvchilar bilan ishlash uchun

app = FastAPI(title="Worky Backend")

# CORS sozlamalari: Netlify va har qanday frontend muammosiz ulanishi uchun
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Netlify'dan kelayotgan so'rovlarga mutloq ruxsat beradi
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Render'da disk o'chib ketmasligi uchun vaqtincha /tmp papkasiga yozamiz
DB = "/tmp/worky.db" if os.environ.get("RENDER") else "worky.db"

# Admin kalitni xavfsiz qilish
ADMIN_KEY = os.environ.get("WORKY_ADMIN_KEY", "WORKY_ADMIN_2026")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


@app.on_event("startup")
def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            phone       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT DEFAULT 'worker',
            is_pro      INTEGER DEFAULT 0,
            pro_until   TEXT,
            token       TEXT UNIQUE,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id),
            amount      INTEGER DEFAULT 50000,
            status      TEXT DEFAULT 'pending',
            screenshot  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            place       TEXT,
            wage        INTEGER,
            time        TEXT,
            category    TEXT,
            is_fake     INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    print("✅ Baza muvaffaqiyatli tayyorlandi!")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token():
    return secrets.token_hex(32)


# ── Models ────────────────────────────────────────────────────────
class RegisterModel(BaseModel):
    name: str
    phone: str
    password: str
    role: str = "worker"


class LoginModel(BaseModel):
    phone: str
    password: str


class ProActivateModel(BaseModel):
    user_id: int
    admin_key: str


class JobCreateModel(BaseModel):
    title: str
    place: str
    wage: int
    time: str
    category: str
    is_fake: int = 0
    admin_key: str  # Faqat admin yangi ish qo'sha olishi uchun


# ── Auth ──────────────────────────────────────────────────────────
@app.post("/auth/register")
def register(data: RegisterModel):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE phone=?", (data.phone,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Bu telefon allaqachon ro'yxatdan o'tgan")

    token = generate_token()
    conn.execute(
        "INSERT INTO users (name, phone, password, role, token) VALUES (?,?,?,?,?)",
        (data.name, data.phone, hash_password(data.password), data.role, token)
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (data.phone,)).fetchone()
    conn.close()
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "phone": user["phone"],
            "role": user["role"],
            "is_pro": bool(user["is_pro"])
        }
    }


@app.post("/auth/login")
def login(data: LoginModel):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE phone=? AND password=?",
        (data.phone, hash_password(data.password))
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Telefon yoki parol noto'g'ri")

    token = generate_token()
    conn.execute("UPDATE users SET token=? WHERE id=?", (token, user["id"]))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "phone": user["phone"],
            "role": user["role"],
            "is_pro": bool(user["is_pro"])
        }
    }


@app.get("/auth/me")
def get_me(token: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    return {
        "id": user["id"],
        "name": user["name"],
        "phone": user["phone"],
        "role": user["role"],
        "is_pro": bool(user["is_pro"]),
        "pro_until": user["pro_until"]
    }


# ── Pro ───────────────────────────────────────────────────────────
@app.post("/pro/request")
def request_pro(token: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")

    conn.execute(
        "INSERT INTO payments (user_id, status) VALUES (?, 'pending')",
        (user["id"],)
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "So'rov yuborildi. @logotipshop10 ga screenshot yuboring!"}


@app.post("/admin/deactivate-pro")
def deactivate_pro(data: ProActivateModel):
    if data.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin kalit noto'g'ri")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (data.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    conn.execute("UPDATE users SET is_pro=0, pro_until=NULL WHERE id=?", (data.user_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"{user['name']} Pro o'chirildi!"}


@app.post("/admin/activate-pro")
def activate_pro(data: ProActivateModel):
    if data.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin kalit noto'g'ri")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (data.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    conn.execute(
        "UPDATE users SET is_pro=1, pro_until=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%d"), data.user_id)
    )
    conn.execute(
        "UPDATE payments SET status='paid' WHERE user_id=? AND status='pending'",
        (data.user_id,)
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"{user['name']} Pro faollashtirildi!"}


# ── Admin panel ───────────────────────────────────────────────────
@app.get("/admin/users")
def get_users(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    users = conn.execute("SELECT id, name, phone, role, is_pro, created_at FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]


@app.get("/admin/payments")
def get_payments(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    payments = conn.execute("""
        SELECT p.*, u.name, u.phone FROM payments p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(p) for p in payments]


# ✨ Yangi ish e'loni qo'shish (Admin uchun yangi endpoint)
@app.post("/admin/add-job")
def add_job(data: JobCreateModel):
    if data.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin kalit noto'g'ri")

    conn = get_db()
    conn.execute(
        "INSERT INTO jobs (title, place, wage, time, category, is_fake) VALUES (?, ?, ?, ?, ?, ?)",
        (data.title, data.place, data.wage, data.time, data.category, data.is_fake)
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"'{data.title}' e'loni muvaffaqiyatli qo'shildi!"}


# ── Jobs ──────────────────────────────────────────────────────────
@app.get("/jobs")
def get_jobs(token: str = None):
    conn = get_db()
    is_pro = False
    if token:
        user = conn.execute("SELECT is_pro FROM users WHERE token=?", (token,)).fetchone()
        if user:
            is_pro = bool(user["is_pro"])

    if is_pro:
        # Pro foydalanuvchilarga hamma toza (haqiqiy) ishlar ko'rinadi
        jobs = conn.execute("SELECT * FROM jobs WHERE is_fake=0 ORDER BY id DESC").fetchall()
    else:
        # Oddiy foydalanuvchilarga hamma ishlar ko'rinadi
        jobs = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()

    conn.close()
    return {"is_pro": is_pro, "jobs": [dict(j) for j in jobs]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import hashlib
import secrets
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Worky Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_KEY = os.environ.get("WORKY_ADMIN_KEY", "WORKY_ADMIN_2026")


def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


@app.on_event("startup")
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'worker',
            is_pro BOOLEAN DEFAULT FALSE,
            pro_until TEXT,
            token TEXT UNIQUE,
            avatar TEXT,
            rating FLOAT DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            verified BOOLEAN DEFAULT FALSE,
            created_at TEXT DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            amount INTEGER DEFAULT 50000,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            employer_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            place TEXT,
            wage INTEGER,
            category TEXT DEFAULT 'Boshqa',
            district TEXT DEFAULT '',
            time_range TEXT,
            slots INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES jobs(id),
            worker_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'pending',
            is_rated BOOLEAN DEFAULT FALSE,
            is_employer_rated BOOLEAN DEFAULT FALSE,
            created_at TEXT DEFAULT current_timestamp,
            UNIQUE(job_id, worker_id)
        );
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            reporter_id INTEGER REFERENCES users(id),
            reported_user_id INTEGER,
            reason TEXT,
            context TEXT,
            created_at TEXT DEFAULT current_timestamp
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ PostgreSQL baza tayyor!")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token():
    return secrets.token_hex(32)


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
    category: str = "Boshqa"
    district: str = ""
    time_range: str = ""
    slots: int = 1

class ApplicationStatusModel(BaseModel):
    application_id: int
    status: str

class UpdateNameModel(BaseModel):
    name: str

class UpdateAvatarModel(BaseModel):
    avatar: str

class RateModel(BaseModel):
    worker_id: Optional[int] = None
    employer_id: Optional[int] = None
    rating: float
    application_id: int

class ReportModel(BaseModel):
    reported_user_id: int
    reason: str
    context: str = ""


@app.post("/auth/register")
def register(data: RegisterModel):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE phone=%s", (data.phone,))
    if cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail="Bu telefon allaqachon ro'yxatdan o'tgan")
    token = generate_token()
    cur.execute(
        "INSERT INTO users (name, phone, password, role, token) VALUES (%s,%s,%s,%s,%s)",
        (data.name, data.phone, hash_password(data.password), data.role, token)
    )
    conn.commit()
    cur.execute("SELECT * FROM users WHERE phone=%s", (data.phone,))
    user = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "token": token, "user": {
        "id": user["id"], "name": user["name"], "phone": user["phone"],
        "role": user["role"], "is_pro": user["is_pro"],
        "rating": user["rating"], "rating_count": user["rating_count"],
        "verified": user["verified"]
    }}


@app.post("/auth/login")
def login(data: LoginModel):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE phone=%s AND password=%s", (data.phone, hash_password(data.password)))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Telefon yoki parol noto'g'ri")
    token = generate_token()
    cur.execute("UPDATE users SET token=%s WHERE id=%s", (token, user["id"]))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "token": token, "user": {
        "id": user["id"], "name": user["name"], "phone": user["phone"],
        "role": user["role"], "is_pro": user["is_pro"],
        "rating": user["rating"], "rating_count": user["rating_count"],
        "verified": user["verified"]
    }}


@app.get("/auth/me")
def get_me(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    return {
        "id": user["id"], "name": user["name"], "phone": user["phone"],
        "role": user["role"], "is_pro": user["is_pro"], "pro_until": user["pro_until"],
        "rating": user["rating"], "rating_count": user["rating_count"],
        "verified": user["verified"]
    }


@app.post("/auth/update")
def update_name(data: UpdateNameModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute("UPDATE users SET name=%s WHERE id=%s", (data.name, user["id"]))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


@app.post("/auth/update-avatar")
def update_avatar(data: UpdateAvatarModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute("UPDATE users SET avatar=%s WHERE id=%s", (data.avatar, user["id"]))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


# 🚀 FRONTENDDA ISHLATILGAN PRO FAOLASHTIRISH ENDPOINTI
@app.post("/auth/upgrade-pro")
def upgrade_pro(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute("UPDATE users SET is_pro=TRUE WHERE id=%s", (user["id"],))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


# FRONTENDDAGI APPREJALARI VA SINCHRONIZATSIYA UCHUN QO'SHIMCHA SINOV ENDPOINTI
@app.post("/users/activate-pro")
def users_activate_pro(token: str):
    return upgrade_pro(token)


@app.post("/pro/request")
def request_pro(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute("INSERT INTO payments (user_id, status) VALUES (%s, 'pending')", (user["id"],))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "message": "So'rov yuborildi!"}


@app.post("/admin/activate-pro")
def activate_pro(data: ProActivateModel):
    if data.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin kalit noto'g'ri")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (data.user_id,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    cur.execute("UPDATE users SET is_pro=TRUE, pro_until=%s WHERE id=%s", (datetime.now().strftime("%Y-%m-%d"), data.user_id))
    cur.execute("UPDATE payments SET status='paid' WHERE user_id=%s AND status='pending'", (data.user_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "message": f"{user['name']} Pro faollashtirildi!"}


@app.get("/admin/users")
def get_users(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, role, is_pro, created_at FROM users ORDER BY id DESC")
    users = cur.fetchall()
    cur.close(); conn.close()
    return [dict(u) for u in users]


# ── JOBS ──────────────────────────────────────────────────────────

@app.post("/jobs/create")
def create_job(data: JobCreateModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute(
        "INSERT INTO jobs (employer_id, title, place, wage, category, district, time_range, slots) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (user["id"], data.title, data.place, data.wage, data.category, data.district, data.time_range, data.slots)
    )
    job_id = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "job_id": job_id}


@app.get("/jobs")
def get_jobs(token: str = None):
    conn = get_db()
    cur = conn.cursor()
    is_pro = False
    if token:
        cur.execute("SELECT is_pro FROM users WHERE token=%s", (token,))
        u = cur.fetchone()
        if u:
            is_pro = bool(u["is_pro"])
    cur.execute("""
        SELECT j.*, u.name as employer_name, u.verified as employer_verified
        FROM jobs j
        LEFT JOIN users u ON u.id = j.employer_id
        WHERE j.status='active'
        ORDER BY j.created_at DESC
    """)
    jobs = cur.fetchall()
    cur.close(); conn.close()
    return {"is_pro": is_pro, "jobs": [dict(j) for j in jobs]}


@app.delete("/jobs/delete/{job_id}")
def delete_job(job_id: int, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("SELECT * FROM jobs WHERE id=%s AND employer_id=%s", (job_id, user["id"]))
    job = cur.fetchone()
    if not job:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Ish topilmadi")
    cur.execute("DELETE FROM applications WHERE job_id=%s", (job_id,))
    cur.execute("DELETE FROM jobs WHERE id=%s", (job_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "message": "Ish o'chirildi!"}


@app.get("/employer/jobs")
def get_employer_jobs(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("SELECT * FROM jobs WHERE employer_id=%s ORDER BY created_at DESC", (user["id"],))
    jobs = cur.fetchall()
    cur.close(); conn.close()
    return [dict(j) for j in jobs]


@app.get("/employer/applications")
def get_employer_applications(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("""
        SELECT a.id, a.status, a.created_at, a.job_id, a.is_rated,
               u.name as worker_name, u.phone as worker_phone, u.id as worker_id,
               u.rating as worker_rating, u.verified as worker_verified,
               j.title as job_title
        FROM applications a
        JOIN users u ON u.id = a.worker_id
        JOIN jobs j ON j.id = a.job_id
        WHERE j.employer_id = %s
        ORDER BY a.created_at DESC
    """, (user["id"],))
    apps = cur.fetchall()
    cur.close(); conn.close()
    return [dict(a) for a in apps]


@app.post("/employer/applications/update")
def update_application(data: ApplicationStatusModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("UPDATE applications SET status=%s WHERE id=%s", (data.status, data.application_id))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


# ── APPLICATIONS ──────────────────────────────────────────────────

@app.post("/apply/{job_id}")
def apply_job(job_id: int, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='worker'", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    # 🔥 Agar foydalanuvchi premium marketing (fake) testlarni ko'rayotgan bo'lsa Pro talab qiladi
    # Real bazadagi e'lonlar uchun ham tekshiruv:
    if not user["is_pro"]:
        cur.close(); conn.close()
        raise HTTPException(status_code=403, detail="Pro kerak")
    try:
        cur.execute("INSERT INTO applications (job_id, worker_id) VALUES (%s,%s)", (job_id, user["id"]))
        conn.commit()
    except:
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail="Allaqachon ariza bergansiz")
    cur.close(); conn.close()
    return {"success": True}


@app.get("/my/applications")
def my_applications(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute("""
        SELECT a.id, a.status, a.job_id, a.is_employer_rated,
               j.title as job_title, j.place, j.wage, j.employer_id,
               u.name as employer_name, u.id as worker_id
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN users u ON u.id = j.employer_id
        WHERE a.worker_id = %s
        ORDER BY a.created_at DESC
    """, (user["id"],))
    apps = cur.fetchall()
    cur.close(); conn.close()
    return [dict(a) for a in apps]


# ── RATING ────────────────────────────────────────────────────────

@app.post("/worker/rate")
def rate_worker(data: RateModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='employer'", (token,))
    employer = cur.fetchone()
    if not employer:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("SELECT * FROM users WHERE id=%s", (data.worker_id,))
    worker = cur.fetchone()
    if not worker:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Ishchi topilmadi")
    new_count = (worker["rating_count"] or 0) + 1
    new_rating = (((worker["rating"] or 0) * (worker["rating_count"] or 0)) + data.rating) / new_count
    cur.execute("UPDATE users SET rating=%s, rating_count=%s WHERE id=%s", (new_rating, new_count, data.worker_id))
    cur.execute("UPDATE applications SET is_rated=TRUE WHERE id=%s", (data.application_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


@app.post("/employer/rate")
def rate_employer(data: RateModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s AND role='worker'", (token,))
    worker = cur.fetchone()
    if not worker:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    cur.execute("SELECT * FROM users WHERE id=%s", (data.employer_id,))
    employer = cur.fetchone()
    if not employer:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Ish beruvchi topilmadi")
    new_count = (employer["rating_count"] or 0) + 1
    new_rating = (((employer["rating"] or 0) * (employer["rating_count"] or 0)) + data.rating) / new_count
    cur.execute("UPDATE users SET rating=%s, rating_count=%s WHERE id=%s", (new_rating, new_count, data.employer_id))
    cur.execute("UPDATE applications SET is_employer_rated=TRUE WHERE id=%s", (data.application_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True}


# ── REPORT ────────────────────────────────────────────────────────

@app.post("/report")
def report_user(data: ReportModel, token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE token=%s", (token,))
    reporter = cur.fetchone()
    if not reporter:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    cur.execute(
        "INSERT INTO reports (reporter_id, reported_user_id, reason, context) VALUES (%s,%s,%s,%s)",
        (reporter["id"], data.reported_user_id, data.reason, data.context)
    )
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "message": "Shikoyat qabul qilindi!"}


@app.get("/admin/reports")
def get_reports(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY created_at DESC")
    reports = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in reports]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

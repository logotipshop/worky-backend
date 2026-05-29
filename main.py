from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
            created_at TEXT DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            amount INTEGER DEFAULT 50000,
            status TEXT DEFAULT 'pending',
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
    return {"success": True, "token": token, "user": {"id": user["id"], "name": user["name"], "phone": user["phone"], "role": user["role"], "is_pro": user["is_pro"]}}


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
    return {"success": True, "token": token, "user": {"id": user["id"], "name": user["name"], "phone": user["phone"], "role": user["role"], "is_pro": user["is_pro"]}}


@app.get("/auth/me")
def get_me(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Token noto'g'ri")
    return {"id": user["id"], "name": user["name"], "phone": user["phone"], "role": user["role"], "is_pro": user["is_pro"], "pro_until": user["pro_until"]}


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


@app.post("/admin/deactivate-pro")
def deactivate_pro(data: ProActivateModel):
    if data.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin kalit noto'g'ri")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_pro=FALSE, pro_until=NULL WHERE id=%s", (data.user_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "message": "Pro o'chirildi!"}


@app.get("/admin/users")
def get_users(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, role, is_pro, created_at FROM users")
    users = cur.fetchall()
    cur.close(); conn.close()
    return [dict(u) for u in users]


@app.get("/admin/payments")
def get_payments(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT p.*, u.name, u.phone FROM payments p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC")
    payments = cur.fetchall()
    cur.close(); conn.close()
    return [dict(p) for p in payments]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

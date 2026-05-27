# Worky Backend

## O'rnatish

```bash
pip install -r requirements.txt
python main.py
```

## API manzillar

### Auth
- POST /auth/register — ro'yxatdan o'tish
- POST /auth/login — kirish
- GET /auth/me?token=... — profil

### Pro
- POST /pro/request?token=... — Pro so'rovi
- POST /admin/activate-pro — Pro faollashtirish

### Admin (admin_key: WORKY_ADMIN_2026)
- GET /admin/users?admin_key=... — barcha foydalanuvchilar
- GET /admin/payments?admin_key=... — to'lovlar

## Admin panel
http://localhost:8000/docs — API dokumentatsiya

## Pro faollashtirish
POST /admin/activate-pro
{
  "user_id": 1,
  "admin_key": "WORKY_ADMIN_2026"
}
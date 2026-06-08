import uuid
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# 🤖 AIOGRAM KUTUBXONALARI
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# 🔑 ASOSIY SOZLAMALAR
BOT_TOKEN = "8774789236:AAGlZSy7dvEOdV3nhKci3k4XF7zxdQvnI44"
FRONTEND_URL = "https://worky-frontend.vercel.app"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 💾 INTEGRATSIYALASHGAN MARKAZLASHGAN BAZA
USERS_DB: Dict[str, dict] = {}
JOBS_DB: List[dict] = [
    {"id": 1, "title": "Mebel sexiga usta kerak", "place": "Grand Mebel", "wage": 250000,
     "category": "Qurilish va Ta'mirlash", "profession": "Mebelchi", "district": "Farg'ona",
     "description": "Kunlik maosh ish tugagach beriladi."},
    {"id": 2, "title": "To'yxonaga shoshilinch ofitsiantlar", "place": "Versal", "wage": 150000,
     "category": "Xizmat koʻrsatish", "profession": "Ofitsiant", "district": "Toshkent",
     "description": "Bugun kechki smenaga. Forma qora shim, oq ko'ylak."},
    {"id": 3, "title": "Brend uchun logotip va korporativ stil", "place": "Logotipshop", "wage": 500000,
     "category": "IT va Dizayn (Masofaviy)", "profession": "Grafik Dizayner", "district": "Masofaviy",
     "description": "Logotipshop - g'oyadan kuchli brendgacha stil yaratish kerak."}
]
REVIEWS_DB: List[dict] = []
CHATS_DB: List[dict] = []


# 🔌 WEBSOCKET CHAT MENEJERI (Real-time xabarlar uchun)
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_token: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_token] = websocket

    def disconnect(self, user_token: str):
        if user_token in self.active_connections:
            del self.active_connections[user_token]

    async def send_personal_message(self, message: dict, user_token: str):
        if user_token in self.active_connections:
            await self.active_connections[user_token].send_json(message)


manager = ConnectionManager()


# ==========================================
# 🤖 1-QISM: TELEGRAM BOT (RO'YXATDAN O'TISH)
# ==========================================
class RegisterState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_rules = State()
    waiting_for_role = State()


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    phone_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]], resize_keyboard=True,
        one_time_keyboard=True)
    await message.answer(
        "<b>🚀 Worky loyihasiga xush kelibsiz!</b>\n\nPlatformadan foydalanish uchun telefon raqamingizni yuboring 👇",
        reply_markup=phone_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_phone)


@dp.message(RegisterState.waiting_for_phone, F.contact)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number, first_name=message.contact.first_name)
    rules_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Qoidalarga roziman va Davom etaman")]],
                                         resize_keyboard=True, one_time_keyboard=True)
    await message.answer(
        "<b>📋 Worky foydalanish qoidalari:</b>\n\n• Ma'lumotlarni to'g'ri kiriting.\n• Kunlik maoshlarni vaqtida to'lang.\n• Firbgarlik qat'iyan man etiladi.",
        reply_markup=rules_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_rules)


@dp.message(RegisterState.waiting_for_rules, F.text == "✅ Qoidalarga roziman va Davom etaman")
async def accept_rules(message: types.Message, state: FSMContext):
    role_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛠️ Ish qidiraman (Xodim)")],
                                                  [KeyboardButton(text="💼 Ishchi qidiraman (Ish beruvchi)")]],
                                        resize_keyboard=True, one_time_keyboard=True)
    await message.answer("<b>⚙️ Profilingiz turini tanlang:</b>", reply_markup=role_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_role)


@dp.message(RegisterState.waiting_for_role,
            F.text.in_({"🛠️ Ish qidiraman (Xodim)", "💼 Ishchi qidiraman (Ish beruvchi)"}))
async def set_role(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    role = "worker" if "🛠️" in message.text else "employer"
    user_token = str(uuid.uuid4())

    USERS_DB[user_token] = {
        "id": message.from_user.id, "name": user_data['first_name'], "phone": user_data['phone'],
        "role": role, "rating": 5.0, "review_count": 0, "bio": "Worky foydalanuvchisi"
    }

    webapp_url = f"{FRONTEND_URL}/?token={user_token}"
    webapp_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Worky ilovasini ochish", web_app=types.WebAppInfo(url=webapp_url))]])
    await message.answer(
        f"<b>🎉 Muvaffaqiyatli roʻyxatdan oʻtdingiz!</b>\n\nIlovani ochish uchun pastdagi tugmani bosing 👇",
        reply_markup=webapp_keyboard, parse_mode="HTML")
    await state.clear()


# ==========================================
# 🌐 2-QISM: FASTAPI BACKEND (ILOVA APILARI)
# ==========================================
class ProfileUpdateRequest(BaseModel):
    name: str
    phone: str
    bio: Optional[str] = None


class JobCreate(BaseModel):
    title: str;
    place: str;
    wage: int;
    category: str;
    profession: str;
    district: str;
    description: str


class ReviewCreate(BaseModel):
    target_user_id: int
    stars: int  # 1 dan 5 gacha
    comment: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Worky Platforma serveri yuklanmoqda...")
    bot_task = asyncio.create_task(dp.start_polling(bot))
    print("🤖 Bot, Chat, Reyting va Profil tizimlari parallel ishga tushdi!")
    yield
    bot_task.cancel()


app = FastAPI(title="Worky Full Platform API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])


# ⚙️ FUNKSIYA 1: PROFIL SOZLAMALARI (Ma'lumotlarni yangilash)
@app.get("/auth/me")
async def get_current_user(token: str):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Noto'g'ri token!")
    return USERS_DB[token]


@app.put("/auth/profile/update")
async def update_profile(token: str, data: ProfileUpdateRequest):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Foydalanuvchi topilmadi!")
    USERS_DB[token]["name"] = data.name
    USERS_DB[token]["phone"] = data.phone
    USERS_DB[token]["bio"] = data.bio
    return {"status": "success", "message": "Profil muvaffaqiyatli yangilandi!", "user": USERS_DB[token]}


# 💼 FUNKSIYA 2: 25+ KASB VA E'LONLAR TIZIMI
@app.get("/jobs")
async def get_all_jobs(token: str, category: Optional[str] = None, profession: Optional[str] = None,
                       district: Optional[str] = None):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Ruxsat yo'q!")
    res = JOBS_DB
    if category: res = [j for j in res if j["category"].lower() == category.lower()]
    if profession: res = [j for j in res if j["profession"].lower() == profession.lower()]
    if district: res = [j for j in res if j["district"].lower() == district.lower()]
    return {"jobs": res}


@app.post("/jobs/create")
async def create_new_job(token: str, job: JobCreate):
    if token not in USERS_DB or USERS_DB[token]["role"] != "employer":
        raise HTTPException(status_code=403, detail="Faqat Ish beruvchilar e'lon joylay oladi!")
    new_id = len(JOBS_DB) + 1
    JOBS_DB.append({"id": new_id, **job.dict()})
    return {"status": "success", "job_id": new_id}


# ⭐️ FUNKSIYA 3: REYTING VA SHARHLAR TIZIMI
@app.post("/reviews/create")
async def create_review(token: str, review: ReviewCreate):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Avval ro'yxatdan o'ting!")
    if review.stars < 1 or review.stars > 5:
        raise HTTPException(status_code=400, detail="Reyting 1 va 5 oraliqda bo'lishi shart!")

    # Maqsadli foydalanuvchini topish va reytingini hisoblash
    target_user = None
    for u in USERS_DB.values():
        if u["id"] == review.target_user_id:
            target_user = u;
            break

    if not target_user:
        raise HTTPException(status_code=404, detail="Bunday foydalanuvchi topilmadi!")

    REVIEWS_DB.append({"sender_id": USERS_DB[token]["id"], **review.dict(), "date": str(datetime.now())})

    # O'rtacha reytingni qayta hisoblash
    total_reviews = [r for r in REVIEWS_DB if r["target_user_id"] == review.target_user_id]
    target_user["review_count"] = len(total_reviews)
    target_user["rating"] = round(sum([r["stars"] for r in total_reviews]) / len(total_reviews), 1)

    return {"status": "success", "new_rating": target_user["rating"]}


# 💬 FUNKSIYA 4: REAL-TIME CHAT (WEBSOCKET ENDPOINT)
@app.websocket("/ws/chat/{token}")
async def websocket_chat_endpoint(websocket: WebSocket, token: str):
    if token not in USERS_DB:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(token, websocket)
    try:
        while True:
            data = await websocket.receive_json()  # Kutilayotgan format: {"to_token": "...", "message": "..."}
            to_token = data.get("to_token")
            msg_text = data.get("message")

            if to_token and msg_text:
                chat_msg = {
                    "from_id": USERS_DB[token]["id"], "from_name": USERS_DB[token]["name"],
                    "message": msg_text, "timestamp": str(datetime.now())
                }
                CHATS_DB.append({"from_token": token, "to_token": to_token, **chat_msg})
                # Qarshi tomonga xabarni srazu yetkazish
                await manager.send_personal_message(chat_msg, to_token)
    except WebSocketDisconnect:
        manager.disconnect(token)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("worky_app:app", host="127.0.0.1", port=8000, reload=False, workers=1)
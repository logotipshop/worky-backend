import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Aiogram kutubxonalari
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Logger sozlamalari
logging.basicConfig(level=logging.INFO)

# 🔑 SIZNING TO'LIQ MA'LUMOTLARINGIZ
BOT_TOKEN = "8774789236:AAGlZSy7dvEOdV3nhKci3k4XF7zxdQvnI44"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "https://worky-frontend.vercel.app"

# Bot va Dispatcher obyektlari
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 💾 Vaqtincha Ma'lumotlar Bazasi
USERS_DB = {}
JOBS_DB = [
    {"id": 1, "title": "Mebel sexiga usta", "place": "Grand Mebel", "wage": 150000, "category": "Qurilish",
     "district": "Farg'ona", "is_fake": False},
    {"id": 2, "title": "Evosga Ofitsiant", "place": "Evos", "wage": 120000, "category": "Restoran",
     "district": "Toshkent", "is_fake": False},
    {"id": 3, "title": "Grafik Dizayner", "place": "Logotipshop", "wage": 350000, "category": "Dizayn",
     "district": "Masofaviy", "is_fake": False},
]


# --- 🤖 TELEGRAM BOT LOGIKASI ---
class RegisterState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_rules = State()
    waiting_for_role = State()


RULES_TEXT = (
    "<b>📋 Worky platformasidan foydalanish shartlari va qoidalari</b>\n\n"
    "<b>1. Foydalanish qoidalari:</b>\n"
    "• <b>Toʻgʻri maʼlumot:</b> Profil ochishda ism va telefon raqamingizni aniq koʻrsating. Yolgʻon maʼlumot bergan profillar bloklanadi.\n"
    "• <b>Rolni toʻgʻri tanlash:</b> Agar siz ish qidirayotgan boʻlsangiz <i>'Ishchi'</i>, e'lon joylashtirmoqchi boʻlsangiz <i>'Ish beruvchi'</i> profilini tanlashingiz shart.\n"
    "• <b>E'lonlar sifati:</b> Joylashtirilayotgan e'lonlarda ish joyi, bajariladigan vazifa, kunlik maosh va viloyat/tuman aniq yozilishi shart.\n"
    "• <b>PRO obuna:</b> Tizimdagi ayrim yuqori maoshli va maxsus e'lonlarni koʻrish hamda arizalar yuborish uchun PRO obunani faollashtirish talab etilishi mumkin.\n\n"
    "<b>2. Xavfsizlik va Mas'uliyat:</b>\n"
    "• <b>Halollik:</b> Ish beruvchilar vaʼda qilingan kunlik maoshni ish yakunlangach, oʻz vaqtida va toʻliq berishi shart.\n"
    "• <b>Taqiqlar:</b> Noqonuniy xizmatlar, qimor, tarmoqli marketing (setevoy) yoki shubhali loyihalar haqida eʼlon joylashtirish qatʼiyan man etiladi.\n"
    "• <b>Ma'lumotlar xavfsizligi:</b> Oʻz profilingiz xavfsizligi uchun maxfiy login yoki botdan berilgan shaxsiy kirish tokenlarini boshqalarga bermang.\n"
    "• <b>Tekshiruv va Mas'uliyat:</b> Ish joyiga borishdan oldin ish beruvchi bilan chat yoki telefon orqali barcha shartlarni toʻliq aniqlashtirib oling. Worky — bu ishchi va ish beruvchini uchrashtiradigan platforma, kelishuvlar tomonlarning oʻz masʼuliyatida boʻladi.\n"
    "• <b>Bloklash (Blacklist):</b> Firbgarlik, haqoratli xabarlar yuborish yoki yolgʻon e'lonlar joylashtirish aniqlansa, foydalanuvchi tizimdan butunlay chetlashtiriladi.\n\n"
    "<i>Tizimdan foydalanish orqali siz ushbu qoidalarga rozilik bildirasiz.</i>"
)


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    phone_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(
        "<b>🚀 Worky loyihasiga xush kelibsiz!</b>\n\nKunbay ishlar platformasidan foydalanish uchun telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_phone)


@dp.message(RegisterState.waiting_for_phone, F.contact)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number, first_name=message.contact.first_name)
    rules_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Qoidalarga roziman va Davom etaman")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(RULES_TEXT, reply_markup=rules_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_rules)


@dp.message(RegisterState.waiting_for_rules, F.text == "✅ Qoidalarga roziman va Davom etaman")
async def accept_rules(message: types.Message, state: FSMContext):
    role_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛠️ Ish qidiraman (Xodim)")],
                  [KeyboardButton(text="💼 Ishchi qidiraman (Ish beruvchi)")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("<b>⚙️ Profilingiz turini tanlang:</b>", reply_markup=role_keyboard, parse_mode="HTML")
    await state.set_state(RegisterState.waiting_for_role)


@dp.message(RegisterState.waiting_for_role,
            F.text.in_({"🛠️ Ish qidiraman (Xodim)", "💼 Ishchi qidiraman (Ish beruvchi)"}))
async def set_role(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    role = "worker" if "🛠️" in message.text else "employer"

    user_token = str(uuid.uuid4())
    USERS_DB[user_token] = {
        "id": message.from_user.id,
        "name": user_data['first_name'],
        "phone": user_data['phone'],
        "role": role,
        "is_pro": False
    }

    webapp_url = f"{FRONTEND_URL}/?token={user_token}"
    webapp_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Worky ilovasini ochish", web_app=types.WebAppInfo(url=webapp_url))]
    ])

    await message.answer(
        f"<b>🎉 Muvaffaqiyatli roʻyxatdan oʻtdingiz!</b>\n\nIlovani ochish uchun pastdagi tugmani bosing 👇",
        reply_markup=webapp_keyboard, parse_mode="HTML"
    )
    await state.clear()


# --- 🌐 FASTAPI BACKEND ENDPOINTLARI ---
class TelegramUserRegister(BaseModel):
    tg_id: int
    name: str
    phone: str
    role: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # KULMINATSION NUQTA: Server yoqilishi bilan Botni parallel fonda ishga tushiramiz
    print("🚀 Worky Backend yuklanmoqda...")
    bot_task = asyncio.create_task(dp.start_polling(bot))
    print("🤖 Telegram Bot fonda muvaffaqiyatli ishga tushdi!")
    yield
    # Server o'chganda botni ham to'xtatamiz
    bot_task.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/telegram-register")
async def telegram_register(user: TelegramUserRegister):
    for uid, udata in USERS_DB.items():
        if udata.get("id") == user.tg_id:
            return {"status": "success", "token": uid}
    user_token = str(uuid.uuid4())
    USERS_DB[user_token] = {"id": user.tg_id, "name": user.name, "phone": user.phone, "role": user.role,
                            "is_pro": False}
    return {"status": "success", "token": user_token}


@app.get("/auth/me")
async def get_current_user(token: str):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Xato token!")
    return USERS_DB[token]


@app.get("/jobs")
async def get_all_jobs(token: str):
    if token not in USERS_DB:
        raise HTTPException(status_code=401, detail="Ruxsat yo'q!")
    return {"jobs": JOBS_DB}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000,
                reload=False)  # Birlashtirilgan kodda reload=False bo'lishi shart
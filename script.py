from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Admin ma'lumotlari
ADMIN_USERNAME = "@logotip10"
ADMIN_PHONE = "+998507558931"

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Buyurtma berish", callback_data='buyurtma')],
        [InlineKeyboardButton("Admin bilan bog‘lanish", callback_data='admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Assalomu alaykum, xush kelibsiz!\nLogotip shop botiga xush kelibsiz 😊",
        reply_markup=reply_markup
    )

# Tugmalar uchun callback
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "buyurtma":
        await query.edit_message_text(
            text=f"Buyurtma berish uchun admin bilan bog‘laning:\n\n"
                 f"Telegram: {ADMIN_USERNAME}\n"
                 f"Telefon: {ADMIN_PHONE}"
        )
    elif query.data == "admin":
        await query.edit_message_text(
            text=f"Admin ma'lumotlari:\nTelegram: {ADMIN_USERNAME}\nTelefon: {ADMIN_PHONE}"
        )

if __name__ == "__main__":
    BOT_TOKEN = "8776187529:AAH_O8V4wqp4qPy9uuDdPYCMpMMdmSWnxAE"

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot ishga tushdi...")
    app.run_polling()
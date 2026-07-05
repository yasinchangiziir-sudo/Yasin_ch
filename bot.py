import os
import json
import random
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8391932958  # ⚠️ آیدی عددی خودت رو جایگزین کن
WEATHER_API_KEY = "کلید_API_آب_و_هوا"  # اختیاری

# ================== فایل یادداشت‌ها ==================
NOTES_FILE = "notes.json"
try:
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        user_notes = json.load(f)
except:
    user_notes = {}

def save_notes():
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(user_notes, f, ensure_ascii=False, indent=2)

# ================== بانک پاسخ‌ها ==================
keywords = {
    "سلام": "سلام! چطور می‌تونم کمکت کنم؟ 😊",
    "خوبی": "مرسی، تو خوبی؟",
    "اسمت چیه": "اسم من Diminol-bot هست، ساخته‌ی یاسین چنگیزی!",
    "جوک بگو": random.choice([
        "چرا برنامه‌نویسا از دریا بدشون میاد؟ چون موج داره! 🌊",
        "یه فیل با یه مورچه دوست میشه، بهش میگه: جا می‌خوای؟",
        "از یه اتم پرسیدن ناهار چی خوردی؟ گفت: هیچی، فقط یه الکترون بود."
    ]),
    "سازنده": "یاسین چنگیزی ساخته منو ❤️",
    "پشتیبانی": None,
}

# ================== وب‌سرور ساده (برای رد کردن چک پورت رندر) ==================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass  # بی‌صدا

def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"🌐 وب‌سرور روی پورت {port} گوش میده...")
    server.serve_forever()

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip() if msg.text else ""

    if text in keywords:
        if text == "پشتیبانی":
            try:
                await context.bot.forward_message(chat_id=OWNER_ID,
                                                  from_chat_id=msg.chat_id,
                                                  message_id=msg.message_id)
                await msg.reply_text("پیامت برای سازنده ارسال شد. 🙏")
            except:
                await msg.reply_text("❌ نتونستم پیام رو به سازنده برسونم.")
        else:
            await msg.reply_text(keywords[text])

    elif text.startswith("هوا "):
        city = text.replace("هوا ", "", 1).strip()
        if WEATHER_API_KEY == "کلید_API_آب_و_هوا":
            await msg.reply_text("کلید API آب‌وهوا تنظیم نشده.")
        else:
            try:
                url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=fa"
                data = requests.get(url, timeout=5).json()
                if data.get("main"):
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    await msg.reply_text(f"🌤 هوای {city}: {temp}°C، {desc}")
                else:
                    await msg.reply_text("شهر پیدا نشد.")
            except:
                await msg.reply_text("خطا در دریافت آب‌وهوا.")

    elif text == "تاس":
        await msg.reply_dice(emoji="🎲")
    elif text == "دارت":
        await msg.reply_dice(emoji="🎯")

    elif text.startswith("یادداشت:"):
        user_id = str(update.effective_user.id)
        note_text = text.replace("یادداشت:", "", 1).strip()
        if note_text:
            user_notes.setdefault(user_id, []).append(note_text)
            save_notes()
            await msg.reply_text("✅ یادداشتت ذخیره شد.")
        else:
            await msg.reply_text("لطفاً متن یادداشت رو بنویس.")

    elif text == "یادداشت‌ها":
        user_id = str(update.effective_user.id)
        notes = user_notes.get(user_id, [])
        if notes:
            reply = "📒 یادداشت‌های تو:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
            await msg.reply_text(reply)
        else:
            await msg.reply_text("هنوز یادداشتی نداری!")

    elif text == "منو":
        keyboard = [
            [InlineKeyboardButton("🎲 تاس", callback_data="dice")],
            [InlineKeyboardButton("🎯 دارت", callback_data="dart")],
            [InlineKeyboardButton("📝 یادداشت جدید", callback_data="note")],
            [InlineKeyboardButton("📒 یادداشت‌های من", callback_data="shownotes")],
            [InlineKeyboardButton("👤 سازنده", callback_data="creator")],
            [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
        ]
        await msg.reply_text("یکی از گزینه‌ها رو انتخاب کن:",
                             reply_markup=InlineKeyboardMarkup(keyboard))

    elif msg.photo:
        await msg.reply_text("تصویر شما دریافت شد.")

    else:
        await msg.reply_text(f"پیام شما: {text}")

# ================== دکمه‌ها ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "dice":
        await query.message.reply_dice(emoji="🎲")
    elif data == "dart":
        await query.message.reply_dice(emoji="🎯")
    elif data == "creator":
        await query.message.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif data == "note":
        await query.message.reply_text("برای ذخیره‌ی یادداشت بنویس: یادداشت: متن")
    elif data == "shownotes":
        user_id = str(query.from_user.id)
        notes = user_notes.get(user_id, [])
        if notes:
            txt = "📒 یادداشت‌های تو:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
            await query.message.reply_text(txt)
        else:
            await query.message.reply_text("هنوز یادداشتی نداری.")
    elif data == "help":
        await query.message.reply_text(
            "🚀 راهنما:\n"
            "- بنویس «سلام» یا «اسمت چیه»\n"
            "- بنویس «سازنده»\n"
            "- بنویس «تاس» یا «دارت»\n"
            "- بنویس «یادداشت: متن» برای ذخیره یادداشت\n"
            "- بنویس «یادداشت‌ها» برای دیدن یادداشت‌ها\n"
            "- بنویس «هوا تهران» برای آب‌وهوا\n"
            "- بنویس «منو» برای دکمه‌ها"
        )

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name}! 🎉")

# ================== اجرای ربات + وب‌سرور ==================
def main():
    # وب‌سرور رو توی یه ترد جدا راه میندازیم
    threading.Thread(target=start_web_server, daemon=True).start()

    # ربات تلگرام
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات قدرتمند اجرا شد...")
    app.run_polling()

if __name__ == "__main__":
    main()

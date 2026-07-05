import os
import json
import random
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from huggingface_hub import InferenceClient

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
HF_API_KEY = os.environ.get("HF_API_KEY")
OWNER_ID = 8391932958  # ⚠️ آیدی عددی خودت
WEATHER_API_KEY = "کلید_API_آب_و_هوا"  # اختیاری

# کلاینت Hugging Face
client = InferenceClient(api_key=HF_API_KEY)

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

# ================== بانک پاسخ‌های کلیدی ==================
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

# ================== وب‌سرور ساختگی ==================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass

def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"🌐 وب‌سرور روی پورت {port} گوش میده...")
    server.serve_forever()

# ================== درخواست به هوش مصنوعی (Hugging Face) ==================
def ask_ai(prompt):
    """ارسال پرامپت به مدل رایگان Mistral"""
    try:
        response = client.text_generation(
            prompt,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_new_tokens=500,
            temperature=0.7,
        )
        return response.strip()
    except Exception as e:
        print(f"❌ خطای Hugging Face: {e}")
        return "متأسفانه مشکلی در ارتباط با هوش مصنوعی پیش اومد."

# ================== تحلیل عکس با هوش مصنوعی ==================
def analyze_image(image_bytes, caption=""):
    """تحلیل عکس با مدل تصویر به متن"""
    try:
        # تبدیل عکس به URL موقت (اختیاری - اینجا از image-to-text استفاده می‌کنیم)
        response = client.image_to_text(
            image_bytes,
            model="Salesforce/blip-image-captioning-base"
        )
        if isinstance(response, list) and len(response) > 0:
            return f"🖼 تحلیل عکس: {response[0].get('generated_text', 'نتونستم تحلیل کنم.')}"
        else:
            return "نتونستم عکس رو تحلیل کنم."
    except Exception as e:
        print(f"❌ خطای تحلیل عکس: {e}")
        return "متأسفانه مشکلی در تحلیل عکس پیش اومد."

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip() if msg.text else ""

    # ۱. پاسخ به کلیدواژه‌ها
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
        return

    # ۲. آب‌وهوا
    if text.startswith("هوا "):
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
        return

    # ۳. بازی‌ها
    if text == "تاس":
        await msg.reply_dice(emoji="🎲")
        return
    if text == "دارت":
        await msg.reply_dice(emoji="🎯")
        return

    # ۴. یادداشت‌ها
    if text.startswith("یادداشت:"):
        user_id = str(update.effective_user.id)
        note_text = text.replace("یادداشت:", "", 1).strip()
        if note_text:
            user_notes.setdefault(user_id, []).append(note_text)
            save_notes()
            await msg.reply_text("✅ یادداشتت ذخیره شد.")
        else:
            await msg.reply_text("لطفاً متن یادداشت رو بنویس.")
        return

    if text == "یادداشت‌ها":
        user_id = str(update.effective_user.id)
        notes = user_notes.get(user_id, [])
        if notes:
            reply = "📒 یادداشت‌های تو:\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
            await msg.reply_text(reply)
        else:
            await msg.reply_text("هنوز یادداشتی نداری!")
        return

    # ۵. منو
    if text == "منو":
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
        return

    # ۶. پردازش عکس با AI
    if msg.photo:
        await msg.reply_text("🔍 در حال تحلیل عکس...")
        try:
            photo_file = await msg.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            caption = msg.caption or ""
            result = analyze_image(bytes(photo_bytes), caption)
            await msg.reply_text(result)
        except Exception as e:
            print(f"❌ خطا در عکس: {e}")
            await msg.reply_text("متأسفانه نتونستم عکس رو تحلیل کنم.")
        return

    # ۷. هوش مصنوعی برای پیام‌های ناشناخته
    await msg.reply_chat_action(action="typing")
    ai_response = ask_ai(text)
    await msg.reply_text(ai_response)

# ================== دکمه‌های شیشه‌ای ==================
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
            "- بنویس «منو» برای دکمه‌ها\n"
            "- **هر سوال دیگه‌ای بپرسی، هوش مصنوعی جوابت رو میده! 🤖**\n"
            "- **عکس بفرستی، برات تحلیلش می‌کنه! 🖼**"
        )

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name}! 🎉")

# ================== اجرا ==================
def main():
    threading.Thread(target=start_web_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات هوشمند (Hugging Face) اجرا شد...")
    app.run_polling()

if __name__ == "__main__":
    main()

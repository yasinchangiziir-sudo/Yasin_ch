import os
import json
import random
import threading
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8391932958  # ⚠️ اینو با آیدی عددی خودت عوض کن

# ================== دیتابیس داخل رندر (JSON) ==================
DATA_FILE = "data.json"
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
except:
    db = {"users": {}, "bad_words": []}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

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
    server.serve_forever()

# ================== توابع کمکی ==================
def get_user(user_id: str):
    return db["users"].get(user_id)

def register_user(user_id: str, username: str, first_name: str):
    if user_id not in db["users"]:
        db["users"][user_id] = {"username": username, "first_name": first_name, "score": 0, "blocked": False}
        save_db()

def add_score(user_id: str):
    if user_id in db["users"]:
        db["users"][user_id]["score"] += 1
        save_db()

def get_top_users():
    sorted_users = sorted(db["users"].items(), key=lambda x: x[1]["score"], reverse=True)
    return sorted_users[:10]

# ================== پنل مدیریت ==================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ دسترسی غیرمجاز.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("دستورات:\n/stats\n/broadcast متن\n/block id\n/unblock id\n/badword add/remove کلمه")
        return
    cmd = args[0].lower()
    if cmd == "stats":
        total = len(db["users"])
        blocked = sum(1 for u in db["users"].values() if u["blocked"])
        await update.message.reply_text(f"👥 کل: {total} | 🚫 مسدود: {blocked}")
    elif cmd == "broadcast" and len(args) > 1:
        msg_text = " ".join(args[1:])
        ok = 0
        for uid in db["users"]:
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📢 پیام مدیر:\n{msg_text}")
                ok += 1
            except:
                pass
        await update.message.reply_text(f"✅ ارسال به {ok} کاربر")
    elif cmd == "block" and len(args) == 2:
        uid = args[1]
        if uid in db["users"]:
            db["users"][uid]["blocked"] = True
            save_db()
            await update.message.reply_text("مسدود شد.")
        else:
            await update.message.reply_text("کاربر پیدا نشد.")
    elif cmd == "unblock" and len(args) == 2:
        uid = args[1]
        if uid in db["users"]:
            db["users"][uid]["blocked"] = False
            save_db()
            await update.message.reply_text("آزاد شد.")
        else:
            await update.message.reply_text("کاربر پیدا نشد.")
    elif cmd == "badword" and len(args) >= 3:
        sub = args[1]
        word = args[2]
        if sub == "add":
            if word not in db["bad_words"]:
                db["bad_words"].append(word)
                save_db()
                await update.message.reply_text(f"کلمه «{word}» اضافه شد.")
        elif sub == "remove":
            if word in db["bad_words"]:
                db["bad_words"].remove(word)
                save_db()
                await update.message.reply_text(f"کلمه «{word}» حذف شد.")
    else:
        await update.message.reply_text("دستور نامعتبر.")

# ================== شروع ==================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(str(user.id), user.username or "", user.first_name or "")
    await update.message.reply_text(f"سلام {user.first_name}! خوش اومدی 🌟")

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    user_id = str(user.id)
    text = msg.text or msg.caption or ""

    # ثبت‌نام
    register_user(user_id, user.username or "", user.first_name or "")

    # بلاک؟
    user_data = get_user(user_id)
    if user_data and user_data["blocked"]:
        return

    # افزایش امتیاز
    add_score(user_id)

    # ضد لینک (گروه)
    if chat.type in ["group", "supergroup"] and text and "http" in text:
        try:
            await msg.delete()
            await msg.reply_text("❌ ارسال لینک ممنوع.", quote=True)
        except:
            pass
        return

    # فیلتر کلمات نامناسب (گروه)
    if chat.type in ["group", "supergroup"] and text:
        for bw in db["bad_words"]:
            if bw in text.lower():
                try:
                    await msg.delete()
                    await msg.reply_text("⛔ پیامت حذف شد (کلمه نامناسب).")
                except:
                    pass
                return

    # دستورات ساده
    if text == "سازنده":
        await msg.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif text == "تاس":
        await msg.reply_dice(emoji="🎲")
    elif text == "دارت":
        await msg.reply_dice(emoji="🎯")
    elif text == "امتیاز":
        u = get_user(user_id)
        await msg.reply_text(f"🌟 امتیاز: {u['score']}")
    elif text == "تاپ":
        top = get_top_users()
        if top:
            txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i, r in enumerate(top))
            await msg.reply_text(txt)
        else:
            await msg.reply_text("کسی نیست.")
    elif text == "منو":
        keyboard = [
            [InlineKeyboardButton("🎲 تاس", callback_data="dice"),
             InlineKeyboardButton("🎯 دارت", callback_data="dart")],
            [InlineKeyboardButton("⭐ امتیاز", callback_data="score"),
             InlineKeyboardButton("🏆 تاپ", callback_data="top")],
            [InlineKeyboardButton("👤 سازنده", callback_data="creator"),
             InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
        ]
        await msg.reply_text("منو:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "قرعه‌کشی" and chat.type in ["group", "supergroup"]:
        try:
            members = [m.user.id async for m in context.bot.get_chat_members(chat.id) if not m.user.is_bot]
            if members:
                winner = random.choice(members)
                await msg.reply_text(f"🎉 برنده: <a href='tg://user?id={winner}'>{winner}</a>", parse_mode="HTML")
        except:
            await msg.reply_text("خطا.")
    elif msg.photo:
        await msg.reply_text("📸 عکس دریافت شد.")
    else:
        await msg.reply_text(f"پیام شما: {text}")

# ================== دکمه‌ها ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(query.from_user.id)
    if data == "dice":
        await query.message.reply_dice(emoji="🎲")
    elif data == "dart":
        await query.message.reply_dice(emoji="🎯")
    elif data == "creator":
        await query.message.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif data == "score":
        u = get_user(user_id)
        await query.message.reply_text(f"🌟 امتیاز: {u['score']}" if u else "نیستی.")
    elif data == "top":
        top = get_top_users()
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i, r in enumerate(top)) if top else "خالیه."
        await query.message.reply_text(txt)
    elif data == "help":
        await query.message.reply_text("راهنما:\n/start\n/admin\nامتیاز - تاپ - تاس - دارت - منو - قرعه‌کشی")

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name} 🌹")

# ================== اجرا ==================
async def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات ساده و قدرتمند اجرا شد.")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

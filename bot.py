import os, json, random, re, asyncio, threading
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8391932958   # ⚠️ آیدی عددی خودت را جایگزین کن

# ================== دیتابیس داخلی ==================
DB_FILE = "bot_data.json"
try:
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
except:
    db = {"users": {}, "bad_words": [], "logs": []}

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def log_action(user_id, action, detail=""):
    db["logs"].append({
        "user_id": user_id,
        "action": action,
        "detail": detail,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    if len(db["logs"]) > 500:
        db["logs"] = db["logs"][-500:]
    save_db()

# ================== وب سرور ساختگی ==================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args): pass

def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# ================== توابع کاربران ==================
def get_user(user_id: str):
    return db["users"].get(user_id)

def register_user(user_id: str, username: str, first_name: str):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": username,
            "first_name": first_name,
            "score": 0,
            "level": 1,
            "blocked": False,
            "notes": [],
            "muted_until": None
        }
        save_db()
    else:
        u = db["users"][user_id]
        u["username"] = username
        u["first_name"] = first_name
        save_db()

def add_score(user_id: str, points: int = 1):
    u = get_user(user_id)
    if u:
        u["score"] += points
        u["level"] = max(1, u["score"] // 100)
        save_db()

def get_top_users(limit=10):
    return sorted(db["users"].items(), key=lambda x: x[1]["score"], reverse=True)[:limit]

def is_muted(user_id: str) -> bool:
    u = get_user(user_id)
    if u and u.get("muted_until"):
        mute_time = datetime.strptime(u["muted_until"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < mute_time:
            return True
        else:
            u["muted_until"] = None
            save_db()
    return False

# ================== ضد اسپم ==================
user_last_messages = defaultdict(list)

def is_spam(user_id: str) -> bool:
    now = datetime.now()
    user_last_messages[user_id] = [t for t in user_last_messages[user_id] if (now - t).seconds < 3]
    if len(user_last_messages[user_id]) >= 5:
        return True
    user_last_messages[user_id].append(now)
    return False

# ================== دستورات ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(str(user.id), user.username or "", user.first_name or "")
    await update.message.reply_text(f"سلام {user.first_name}! خوش اومدی 🌟")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 راهنما:\n"
        "/start - ثبت‌نام\n"
        "/admin - پنل مدیریت\n"
        "/mute - سکوت کاربر\n"
        "/poll - نظرسنجی\n"
        "/remind - یادآوری\n"
        "امتیاز - تاپ - تاس - دارت - منو - قرعه‌کشی - یادداشت"
    )

# ================== پنل ادمین ==================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ دسترسی غیرمجاز.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("دستورات: stats / broadcast / block / unblock / badword / logs")
        return
    cmd = args[0].lower()
    if cmd == "stats":
        total = len(db["users"])
        blocked = sum(1 for u in db["users"].values() if u["blocked"])
        await update.message.reply_text(f"👥 کل: {total} | 🚫 مسدود: {blocked}")
    elif cmd == "broadcast" and len(args) > 1:
        text = " ".join(args[1:])
        ok = 0
        for uid in db["users"]:
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📢 {text}")
                ok += 1
            except: pass
        await update.message.reply_text(f"✅ ارسال به {ok} کاربر")
    elif cmd == "block" and len(args) == 2:
        uid = args[1]
        u = get_user(uid)
        if u:
            u["blocked"] = True
            save_db()
            await update.message.reply_text("کاربر مسدود شد.")
        else:
            await update.message.reply_text("پیدا نشد.")
    elif cmd == "unblock" and len(args) == 2:
        uid = args[1]
        u = get_user(uid)
        if u:
            u["blocked"] = False
            save_db()
            await update.message.reply_text("کاربر آزاد شد.")
        else:
            await update.message.reply_text("پیدا نشد.")
    elif cmd == "badword" and len(args) >= 3:
        sub, word = args[1], args[2]
        if sub == "add":
            if word not in db["bad_words"]:
                db["bad_words"].append(word)
                save_db()
                await update.message.reply_text(f"«{word}» اضافه شد.")
        elif sub == "remove":
            if word in db["bad_words"]:
                db["bad_words"].remove(word)
                save_db()
                await update.message.reply_text(f"«{word}» حذف شد.")
    elif cmd == "logs":
        recent = db["logs"][-20:]
        txt = "📝 آخرین لاگ‌ها:\n" + "\n".join(f"{l['time']} | {l['action']} | {l['detail'][:30]}" for l in recent)
        await update.message.reply_text(txt[:4000])
    else:
        await update.message.reply_text("دستور نامعتبر.")

# ================== Mute ==================
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("فقط توی گروه.")
        return
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"] and user.id != OWNER_ID:
        await update.message.reply_text("❌ فقط ادمین‌ها.")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("/mute user_id دقیقه")
        return
    target_id = context.args[0]
    try:
        minutes = int(context.args[1])
    except:
        await update.message.reply_text("مدت نامعتبر.")
        return
    target = get_user(target_id)
    if not target:
        await update.message.reply_text("کاربر ثبت‌نام نکرده.")
        return
    until = datetime.now() + timedelta(minutes=minutes)
    target["muted_until"] = until.strftime("%Y-%m-%d %H:%M:%S")
    save_db()
    await update.message.reply_text(f"🔇 کاربر {target_id} برای {minutes} دقیقه بی‌صدا شد.")

# ================== Poll ==================
async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_text("/poll سوال | گزینه۱, گزینه۲,...")
        return
    question, opts = text.split("|", 1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options) < 2:
        await update.message.reply_text("حداقل ۲ گزینه.")
        return
    await update.message.reply_poll(question=question.strip(), options=options, is_anonymous=True)

# ================== Remind ==================
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/remind 10m پیام")
        return
    try:
        delay_str = context.args[0]
        message = " ".join(context.args[1:])
        if not message:
            await update.message.reply_text("متن یادآوری را بنویس.")
            return
        unit = delay_str[-1].lower()
        amount = int(delay_str[:-1])
        if unit == 's': seconds = amount
        elif unit == 'm': seconds = amount * 60
        elif unit == 'h': seconds = amount * 3600
        else:
            await update.message.reply_text("واحد نامعتبر.")
            return
        await update.message.reply_text(f"⏰ یادآوری برای {amount}{unit} دیگر تنظیم شد.")
        await asyncio.sleep(seconds)
        await update.message.reply_text(f"🔔 یادآوری:\n{message}")
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    user_id = str(user.id)
    text = msg.text or msg.caption or ""

    register_user(user_id, user.username or "", user.first_name or "")
    u = get_user(user_id)

    if u and u["blocked"]:
        return
    if is_muted(user_id):
        try: await msg.delete()
        except: pass
        return

    log_action(user_id, "message", text[:50])

    if chat.type in ["group", "supergroup"]:
        if is_spam(user_id):
            try:
                await msg.delete()
                await msg.reply_text("❌ اسپم نکنید.")
            except: pass
            return

    if chat.type in ["group", "supergroup"] and re.search(r'https?://', text):
        try:
            await msg.delete()
            await msg.reply_text("❌ لینک ممنوع.", quote=True)
        except: pass
        return

    if chat.type in ["group", "supergroup"]:
        for bw in db["bad_words"]:
            if bw in text.lower():
                try:
                    await msg.delete()
                    await msg.reply_text("⛔ پیام حذف شد (کلمه نامناسب).")
                except: pass
                return

    add_score(user_id)

    if text == "سازنده":
        await msg.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif text == "تاس":
        await msg.reply_dice(emoji="🎲")
    elif text == "دارت":
        await msg.reply_dice(emoji="🎯")
    elif text == "امتیاز":
        await msg.reply_text(f"🌟 امتیاز: {u['score']} | سطح: {u['level']}")
    elif text == "تاپ":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i, r in enumerate(top)) if top else "خالی."
        await msg.reply_text(txt)
    elif text.startswith("یادداشت:"):
        note = text.replace("یادداشت:", "", 1).strip()
        if note:
            u["notes"].append(note)
            save_db()
            await msg.reply_text("✅ ذخیره شد.")
    elif text == "یادداشت‌ها":
        notes = u.get("notes", [])
        await msg.reply_text("📒 یادداشت‌ها:\n" + "\n".join(f"• {n}" for n in notes) if notes else "یادداشتی نداری.")
    elif text == "منو":
        keyboard = [
            [InlineKeyboardButton("🎲 تاس", callback_data="dice"), InlineKeyboardButton("🎯 دارت", callback_data="dart")],
            [InlineKeyboardButton("⭐ امتیاز", callback_data="score"), InlineKeyboardButton("🏆 تاپ", callback_data="top")],
            [InlineKeyboardButton("👤 سازنده", callback_data="creator"), InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
        ]
        await msg.reply_text("منو:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "قرعه‌کشی" and chat.type in ["group", "supergroup"]:
        try:
            members = [m.user.id async for m in context.bot.get_chat_members(chat.id) if not m.user.is_bot]
            winner = random.choice(members)
            await msg.reply_text(f"🎉 برنده: <a href='tg://user?id={winner}'>{winner}</a>", parse_mode="HTML")
        except: pass
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
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i, r in enumerate(top)) if top else "خالی."
        await query.message.reply_text(txt)
    elif data == "help":
        await query.message.reply_text("/start\n/admin\n/mute\n/poll\n/remind\nامتیاز - تاپ - تاس - دارت - منو")

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name} 🌹")

# ================== اجرا ==================
def main():
    # اجرای وب‌سرور در یک thread جداگانه
    threading.Thread(target=start_web_server, daemon=True).start()
    # ساخت اپلیکیشن
    app = Application.builder().token(BOT_TOKEN).build()
    # افزودن هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("poll", poll_command))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات کامل و بدون هوش مصنوعی اجرا شد.")
    app.run_polling()

if __name__ == "__main__":
    main()

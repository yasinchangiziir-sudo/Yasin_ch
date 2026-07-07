import os, json, random, re, asyncio, threading
from datetime import datetime, timedelta, time as dt_time
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import jdatetime
import requests as http_req
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8391932958          # ⚠️ آیدی عددی خودت
ADMIN_USERNAME = "@YasinChangizi"   # ⚠️ یوزرنیم یا آیدی خودت
NAVASAN_API_KEY = os.environ.get("NAVASAN_API_KEY", "")
CHANNEL_LINK = "https://t.me/YasinChangizi"   # ⚠️ لینک کانال خودت

# ================== دیتابیس ==================
DB_FILE = "bot_data.json"
try:
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
except:
    db = {}
db.setdefault("users", {})
db.setdefault("bad_words", [])
db.setdefault("logs", [])
db.setdefault("jokes", [])
db.setdefault("quotes", [])
db.setdefault("learned", {})
db.setdefault("stickers", [])
db.setdefault("animations", [])
db.setdefault("files", [])
db.setdefault("group_diaries", {})
db.setdefault("referrals", {})
db.setdefault("shop", [])
db.setdefault("user_items", {})
db.setdefault("pets", {})
db.setdefault("quests", {
    "templates": [
        {"id":1, "desc": "۳ تا جوک بگو"},
        {"id":2, "desc": "با ۵ نفر چت کن"},
        {"id":3, "desc": "یه قرعه‌کشی انجام بده"},
        {"id":4, "desc": "امتیازت رو به ۵۰ برسون"},
        {"id":5, "desc": "یه یادداشت جدید بنویس"},
    ]
})
db.setdefault("group_games", {})
db.setdefault("inline_polls", {})
db.setdefault("bot_active", True)
db.setdefault("daily_reward_date", "")
db.setdefault("warnings", {})
db.setdefault("guess_character", {})
db.setdefault("active_chats", [])
db.setdefault("math_games", {})
db.setdefault("scheduled_jobs", [])
db.setdefault("anon_waiting", {})
db.setdefault("ticket_waiting", {})
db.setdefault("used_yasin", [])
db.setdefault("group_data", {})
db.setdefault("daily_rolls", {})
db.setdefault("snake_games", {})
db.setdefault("weekly_stats", {})
db.setdefault("millionaire_games", {})

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

# ================== وب‌سرور ==================
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

def register_user(user_id: str, username: str, first_name: str, referrer_id: str = None):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": username, "first_name": first_name,
            "score": 0, "level": 1, "blocked": False,
            "notes": [], "muted_until": None, "birthday": None, "role": None
        }
        if referrer_id == "yasin":
            add_score(user_id, 500)
            log_action(user_id, "special_referral", "کد yasin")
        elif referrer_id and referrer_id.isdigit() and referrer_id in db["users"] and referrer_id != user_id:
            db["referrals"].setdefault(referrer_id, {"count": 0, "invited": []})
            db["referrals"][referrer_id]["count"] += 1
            db["referrals"][referrer_id]["invited"].append(user_id)
            add_score(referrer_id, 20)
        save_db()
    else:
        u = db["users"][user_id]
        u["username"] = username
        u["first_name"] = first_name
        save_db()

def add_score(user_id: str, points=1):
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

def get_user_title(score: int, role: str = None) -> str:
    if role: return role
    if score < 100: return "🟢 تازه‌وارد"
    elif score < 300: return "🔵 فعال"
    elif score < 600: return "🟣 حرفه‌ای"
    else: return "👑 افسانه‌ای"

# ================== ضد اسپم ==================
user_last_messages = defaultdict(list)
def is_spam(user_id: str) -> bool:
    now = datetime.now()
    user_last_messages[user_id] = [t for t in user_last_messages[user_id] if (now - t).seconds < 3]
    if len(user_last_messages[user_id]) >= 5:
        return True
    user_last_messages[user_id].append(now)
    return False

# ================== خاموش/روشن ==================
async def check_bot_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db["bot_active"] and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🪫 ربات در حال تعمیر است.")
        return True
    return False

# ================== تابع کمکی ارسال پیام بلند ==================
async def send_long_message(chat_id, text, bot, max_len=4000):
    for i in range(0, len(text), max_len):
        await bot.send_message(chat_id=chat_id, text=text[i:i+max_len])

# ================== منوهای شیشه‌ای ==================
def get_main_menu_keyboard(user_id: int = None):
    keyboard = [
        [InlineKeyboardButton("🎮 بازی‌ها", callback_data="menu_games")],
        [InlineKeyboardButton("🛠 ابزارها", callback_data="menu_tools")],
        [InlineKeyboardButton("👤 پروفایل", callback_data="menu_profile")],
        [InlineKeyboardButton("👥 گروه", callback_data="menu_group")],
        [InlineKeyboardButton("📁 فایل‌ها", callback_data="menu_files")],
        [InlineKeyboardButton("🎫 تیکت پشتیبانی", callback_data="ticket_start")],
        [InlineKeyboardButton("💬 چت ناشناس", callback_data="anon_chat")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data="menu_admin")])
    keyboard.append([InlineKeyboardButton("ℹ️ راهنما", callback_data="help")])
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 تاس", callback_data="dice"), InlineKeyboardButton("🎯 دارت", callback_data="dart")],
        [InlineKeyboardButton("✂️ سنگ کاغذ قیچی", callback_data="rps_menu")],
        [InlineKeyboardButton("🪙 شیر یا خط", callback_data="coinflip")],
        [InlineKeyboardButton("🎱 توپ جادویی", callback_data="magic8_menu")],
        [InlineKeyboardButton("🔢 مسابقه ریاضی", callback_data="mathquiz")],
        [InlineKeyboardButton("🔤 حدس کلمه", callback_data="guessword_menu")],
        [InlineKeyboardButton("👤 حدس شخصیت", callback_data="guesswho_menu")],
        [InlineKeyboardButton("⭕ دوز", callback_data="duel_menu")],
        [InlineKeyboardButton("🐍 مار و پله", callback_data="snake_menu")],
        [InlineKeyboardButton("🎡 چرخ شانس", callback_data="roll_menu")],
        [InlineKeyboardButton("💰 میلیونر", callback_data="millionaire_menu")],
        [InlineKeyboardButton("🐣 پت مجازی", callback_data="pet_menu")],
        [InlineKeyboardButton("🎯 مأموریت‌ها", callback_data="quests_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

def get_tools_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 قیمت دلار", callback_data="price_dollar"), InlineKeyboardButton("🥇 سکه", callback_data="price_coin"), InlineKeyboardButton("💍 طلا", callback_data="price_gold")],
        [InlineKeyboardButton("📋 نظرسنجی", callback_data="poll_menu"), InlineKeyboardButton("📊 نظرسنجی دکمه‌ای", callback_data="pollbtn_menu")],
        [InlineKeyboardButton("⏰ یادآوری", callback_data="remind_menu"), InlineKeyboardButton("⏳ تایمر", callback_data="timer_menu")],
        [InlineKeyboardButton("📝 یادداشت", callback_data="note_menu"), InlineKeyboardButton("📒 یادداشت‌ها", callback_data="shownotes")],
        [InlineKeyboardButton("📜 فال", callback_data="fal_menu"), InlineKeyboardButton("🎯 چالش", callback_data="challenge_menu")],
        [InlineKeyboardButton("📅 امروز", callback_data="today")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

def get_profile_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ امتیاز", callback_data="score"), InlineKeyboardButton("🏆 تاپ", callback_data="top")],
        [InlineKeyboardButton("📒 یادداشت‌ها", callback_data="shownotes")],
        [InlineKeyboardButton("🛍 فروشگاه", callback_data="menu_shop"), InlineKeyboardButton("🎁 آیتم‌ها", callback_data="items_menu")],
        [InlineKeyboardButton("🐣 حیوان خانگی", callback_data="pet_status"), InlineKeyboardButton("🎂 تولد", callback_data="birthday_menu")],
        [InlineKeyboardButton("🔗 کد دعوت", callback_data="referral_menu"), InlineKeyboardButton("👤 whois", callback_data="whois_menu")],
        [InlineKeyboardButton("👥 دعوت‌شده‌ها", callback_data="myreferrals")],
        [InlineKeyboardButton("🧹 پاک کردن یادداشت", callback_data="clearnotes")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

def get_group_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔇 سکوت", callback_data="mute_menu"), InlineKeyboardButton("⚠️ اخطار", callback_data="warn_menu")],
        [InlineKeyboardButton("📋 اخطارها", callback_data="warns_menu"), InlineKeyboardButton("🔄 پاک اخطار", callback_data="resetwarn_menu")],
        [InlineKeyboardButton("🔒 قفل", callback_data="lock_menu"), InlineKeyboardButton("🔓 باز کردن", callback_data="unlock_menu")],
        [InlineKeyboardButton("📖 داستان", callback_data="story_menu")],
        [InlineKeyboardButton("📓 خاطرات", callback_data="diary_menu"), InlineKeyboardButton("🏆 تالار", callback_data="hall_menu")],
        [InlineKeyboardButton("🖼 گالری", callback_data="gallery_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="admin_stats"), InlineKeyboardButton("📢 همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 مسدود", callback_data="admin_block"), InlineKeyboardButton("✅ آزاد", callback_data="admin_unblock")],
        [InlineKeyboardButton("🔇 فیلتر", callback_data="admin_badword")],
        [InlineKeyboardButton("📝 لاگ", callback_data="admin_logs")],
        [InlineKeyboardButton("🧠 یاد بده", callback_data="learn_menu"), InlineKeyboardButton("🗑 پاک حرف", callback_data="unlearn_menu")],
        [InlineKeyboardButton("😄 افزودن جوک", callback_data="addjoke_menu"), InlineKeyboardButton("🗑 حذف جوک", callback_data="deljoke_menu")],
        [InlineKeyboardButton("💬 افزودن نقل‌قول", callback_data="addquote_menu"), InlineKeyboardButton("🗑 حذف نقل‌قول", callback_data="delquote_menu")],
        [InlineKeyboardButton("📋 جوک‌ها", callback_data="jokes_list"), InlineKeyboardButton("📋 نقل‌قول‌ها", callback_data="quotes_list")],
        [InlineKeyboardButton("🛍 فروشگاه", callback_data="shop_manage")],
        [InlineKeyboardButton("👑 نقش", callback_data="role_menu"), InlineKeyboardButton("⏰ زمان‌بندی", callback_data="schedule_menu")],
        [InlineKeyboardButton("🎁 هدیه", callback_data="dailyreward_btn"), InlineKeyboardButton("🔌 خاموش", callback_data="bot_toggle")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

# ================== دستور start ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = context.args[0] if context.args else None
    user_id = str(user.id)

    if user_id not in db["users"]:
        register_user(user_id, user.username or "", user.first_name or "", referrer_id)
    else:
        if referrer_id == "yasin" and user_id not in db["used_yasin"]:
            add_score(user_id, 500)
            db["used_yasin"].append(user_id)
            save_db()
            await update.message.reply_text("🎉 ۵۰۰ امتیاز ویژه به شما تعلق گرفت!")

    await update.message.reply_text(
        f"🤖 **به Diminol-bot خوش اومدی!**\n ❤️\n\n"
        f"📖 برای دریافت راهنمای کامل دستورات به کانال زیر مراجعه کنید:\n{CHANNEL_LINK}\n\n"
        f"یا بنویس منو تا دکمه‌های شیشه‌ای را ببینی.",
        reply_markup=get_main_menu_keyboard(update.effective_user.id),
        disable_web_page_preview=True
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
        uid = args[1]; u = get_user(uid)
        if u:
            u["blocked"] = True; save_db()
            await update.message.reply_text("کاربر مسدود شد.")
            try:
                await context.bot.send_message(int(uid), "🚫 شما توسط سازنده ربات مسدود شده‌اید.")
            except: pass
        else: await update.message.reply_text("پیدا نشد.")
    elif cmd == "unblock" and len(args) == 2:
        uid = args[1]; u = get_user(uid)
        if u: u["blocked"] = False; save_db(); await update.message.reply_text("کاربر آزاد شد.")
        else: await update.message.reply_text("پیدا نشد.")
    elif cmd == "badword" and len(args) >= 3:
        sub, word = args[1], args[2]
        if sub == "add":
            if word not in db["bad_words"]: db["bad_words"].append(word); save_db(); await update.message.reply_text(f"«{word}» اضافه شد.")
        elif sub == "remove":
            if word in db["bad_words"]: db["bad_words"].remove(word); save_db(); await update.message.reply_text(f"«{word}» حذف شد.")
    elif cmd == "logs":
        recent = db["logs"][-20:]
        txt = "📝 آخرین لاگ‌ها:\n" + "\n".join(f"{l['time']} | {l['action']} | {l['detail'][:30]}" for l in recent)
        await update.message.reply_text(txt[:4000])
    else:
        await update.message.reply_text("دستور نامعتبر.")

# ================== خاموش/روشن و هدیه روزانه ==================
async def bot_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args or context.args[0] not in ("on", "off"): return await update.message.reply_text("/bot on / off")
    db["bot_active"] = context.args[0] == "on"
    save_db()
    await update.message.reply_text(f"✅ ربات {'روشن' if db['bot_active'] else 'خاموش'} شد.")

async def daily_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    today = datetime.now().strftime("%Y-%m-%d")
    if db["daily_reward_date"] == today: return await update.message.reply_text("امروز جایزه داده شده.")
    top = get_top_users(1)
    if top:
        winner_id = top[0][0]
        add_score(winner_id, 50)
        db["daily_reward_date"] = today; save_db()
        await update.message.reply_text(f"🎉 ۵۰ امتیاز به {top[0][1]['first_name']} داده شد!")
    else:
        await update.message.reply_text("کاربری نیست.")

# ================== Mute / Poll / Remind ==================
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator","creator"] and user.id != OWNER_ID: return await update.message.reply_text("❌ فقط ادمین.")
    if not context.args or len(context.args) < 2: return await update.message.reply_text("/mute user_id دقیقه")
    target_id = context.args[0]
    try: minutes = int(context.args[1])
    except: return await update.message.reply_text("مدت نامعتبر.")
    target = get_user(target_id)
    if not target: return await update.message.reply_text("کاربر ثبت‌نام نکرده.")
    until = datetime.now() + timedelta(minutes=minutes)
    target["muted_until"] = until.strftime("%Y-%m-%d %H:%M:%S")
    save_db()
    await update.message.reply_text(f"🔇 کاربر {target_id} برای {minutes} دقیقه بی‌صدا شد.")
    chat_id = str(chat.id)
    db["weekly_stats"].setdefault(chat_id, {"messages": 0, "mutes": 0, "links_deleted": 0})
    db["weekly_stats"][chat_id]["mutes"] += 1
    save_db()

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/poll سوال | گزینه۱, گزینه۲,...")
    question, opts = text.split("|",1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options)<2: return await update.message.reply_text("حداقل ۲ گزینه.")
    await update.message.reply_poll(question=question.strip(), options=options, is_anonymous=True)

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args: return await update.message.reply_text("/remind 10m پیام")
    try:
        delay_str = context.args[0]
        message = " ".join(context.args[1:])
        if not message: return await update.message.reply_text("متن یادآوری را بنویس.")
        unit = delay_str[-1].lower(); amount = int(delay_str[:-1])
        if unit == 's': seconds = amount
        elif unit == 'm': seconds = amount*60
        elif unit == 'h': seconds = amount*3600
        else: return await update.message.reply_text("واحد نامعتبر.")
        await update.message.reply_text(f"⏰ یادآوری برای {amount}{unit} دیگر تنظیم شد.")
        await asyncio.sleep(seconds)
        await update.message.reply_text(f"🔔 یادآوری:\n{message}")
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")

# ================== یادگیری و جُک ==================
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/learn کلمه | پاسخ")
    trigger, response = text.split("|",1)
    trigger = trigger.strip(); response = response.strip()
    if not trigger or not response: return await update.message.reply_text("کلمه و پاسخ خالی نباشن.")
    db["learned"][trigger] = response
    save_db()
    await update.message.reply_text(f"✅ یادم اومد به «{trigger}» بگم:\n{response}")

async def unlearn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args: return await update.message.reply_text("/unlearn کلمه")
    trigger = context.args[0]
    if trigger in db["learned"]:
        del db["learned"][trigger]; save_db()
        await update.message.reply_text(f"«{trigger}» از حافظه پاک شد.")
    else:
        await update.message.reply_text("این کلمه تو حافظه نیست.")

async def addjoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    joke = " ".join(context.args)
    if not joke: return await update.message.reply_text("/addjoke متن جُک")
    db["jokes"].append(joke); save_db()
    await update.message.reply_text(f"✅ جُک جدید ذخیره شد. (شماره {len(db['jokes'])})")

async def deljoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده میتونه حذف کنه.")
    if not context.args: return await update.message.reply_text("/deljoke شماره")
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["jokes"]):
            removed = db["jokes"].pop(idx); save_db()
            await update.message.reply_text(f"جُک حذف شد: {removed}")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("عدد وارد کن.")

async def list_jokes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = db["jokes"]
    if not jokes: return await update.message.reply_text("هنوز هیچ جُکی نیست.")
    txt = "📋 لیست جُوک‌ها:\n" + "\n".join(f"{i+1}. {j}" for i,j in enumerate(jokes))
    await update.message.reply_text(txt[:4000])

# ================== نقل‌قول‌ها ==================
async def addquote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote = " ".join(context.args)
    if not quote: return await update.message.reply_text("/addquote متن نقل‌قول")
    db["quotes"].append(quote)
    save_db()
    await update.message.reply_text(f"✅ نقل‌قول جدید ذخیره شد. (شماره {len(db['quotes'])})")

async def delquote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده میتونه حذف کنه.")
    if not context.args: return await update.message.reply_text("/delquote شماره")
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["quotes"]):
            removed = db["quotes"].pop(idx); save_db()
            await update.message.reply_text(f"نقل‌قول حذف شد: {removed}")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("عدد وارد کن.")

async def list_quotes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quotes = db["quotes"]
    if not quotes: return await update.message.reply_text("هنوز نقل‌قولی ثبت نشده.")
    txt = "📋 لیست نقل‌قول‌ها:\n" + "\n".join(f"{i+1}. {q}" for i,q in enumerate(quotes))
    await update.message.reply_text(txt[:4000])

# ================== فروشگاه ==================
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    shop = db["shop"]
    if not shop: return await update.message.reply_text("فروشگاه خالیه.")
    txt = "🛍 فروشگاه:\n"
    for i, item in enumerate(shop, 1):
        stock = item.get("stock", "نامحدود")
        txt += f"{i}. {item['name']} - 💰 {item['price']} | 📦 {stock}\n"
    await update.message.reply_text(txt)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id); u = get_user(user_id)
    if not u: return await update.message.reply_text("/start")
    if not context.args: return await update.message.reply_text("/buy شماره")
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["shop"]):
            item = db["shop"][idx]
            stock = item.get("stock")
            if stock is not None and stock <= 0:
                return await update.message.reply_text("❌ موجودی این آیتم تمام شده.")
            if u["score"] >= item["price"]:
                u["score"] -= item["price"]
                if stock is not None:
                    item["stock"] -= 1
                db["user_items"].setdefault(user_id, []).append(item["name"])
                save_db()
                await update.message.reply_text(f"✅ {item['name']} خریداری شد!")
            else: await update.message.reply_text("❌ امتیاز کافی نداری.")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("خطا در خرید.")

async def my_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    items = db["user_items"].get(user_id, [])
    if items: await update.message.reply_text("🎁 آیتم‌های شما:\n" + "\n".join(f"• {i}" for i in items))
    else: await update.message.reply_text("هنوز چیزی نخریدی.")

async def additem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    args = context.args
    if len(args) < 2: return await update.message.reply_text("/additem <نام> <قیمت> [موجودی]")
    try:
        if len(args) >= 3 and args[-2].isdigit() and args[-1].isdigit():
            stock = int(args[-2])
            price = int(args[-1])
            name = " ".join(args[:-2])
        else:
            price = int(args[-1])
            stock = None
            name = " ".join(args[:-1])
    except:
        return await update.message.reply_text("فرمت اشتباه. مثال: /additem شمشیر 300 5")
    db["shop"].append({"name": name, "price": price, "stock": stock})
    save_db()
    await update.message.reply_text(f"✅ آیتم «{name}» با قیمت {price} اضافه شد.")

async def removeitem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args: return await update.message.reply_text("/removeitem شماره")
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["shop"]):
            removed = db["shop"].pop(idx); save_db()
            await update.message.reply_text(f"آیتم «{removed['name']}» حذف شد.")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("عدد وارد کن.")

async def editprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    args = context.args
    if len(args) < 2: return await update.message.reply_text("/editprice <شماره> <قیمت جدید>")
    try:
        idx = int(args[0]) - 1; new_price = int(args[1])
        if 0 <= idx < len(db["shop"]):
            db["shop"][idx]["price"] = new_price; save_db()
            await update.message.reply_text(f"✅ قیمت «{db['shop'][idx]['name']}» به {new_price} تغییر کرد.")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("اعداد معتبر وارد کن.")

# ================== نقش کاربران ==================
async def role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args or len(context.args) < 2: return await update.message.reply_text("/role user_id نقش")
    target_id = context.args[0]
    role = " ".join(context.args[1:])
    u = get_user(target_id)
    if not u: return await update.message.reply_text("کاربر پیدا نشد.")
    u["role"] = role
    save_db()
    await update.message.reply_text(f"✅ نقش «{role}» به کاربر {target_id} داده شد.")

async def unrole_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args: return await update.message.reply_text("/unrole user_id")
    target_id = context.args[0]
    u = get_user(target_id)
    if not u: return await update.message.reply_text("کاربر پیدا نشد.")
    u["role"] = None
    save_db()
    await update.message.reply_text("✅ نقش کاربر پاک شد.")

# ================== چرخ شانس ==================
ROLL_PRIZES = [10, 20, 30, 50, 100, 0, 5, 15, 25, 0]
async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    if db["daily_rolls"].get(user_id) == today:
        await update.message.reply_text("❌ امروز یک‌بار چرخ شانس رو زدی! فردا دوباره بیا.")
        return
    prize = random.choice(ROLL_PRIZES)
    db["daily_rolls"][user_id] = today
    if prize > 0:
        add_score(user_id, prize)
        await update.message.reply_text(f"🎡 چرخ شانس: {prize} امتیاز گرفتی! 🎉")
    else:
        await update.message.reply_text(f"🎡 چرخ شانس: متأسفانه جایزه‌ای برنده نشدی. 😕")
    save_db()

# ================== مار و پله ==================
SNAKE_BOARD = {3: 11, 8: 17, 16: 4, 21: 9, 27: 1}
async def snake_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    chat_id = str(chat.id)
    if chat_id in db["snake_games"]:
        await update.message.reply_text("یه بازی مار و پله در حال انجامه!")
        return
    db["snake_games"][chat_id] = {}
    save_db()
    await update.message.reply_text("🐍 بازی مار و پله شروع شد! با /dice تاس بندازید.")

async def snake_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_id = str(chat.id)
    game = db["snake_games"].get(chat_id)
    if game is None: return
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in game:
        game[user_id] = 0
    dice = random.randint(1, 6)
    new_pos = game[user_id] + dice
    if new_pos > 30: new_pos = 30
    if new_pos in SNAKE_BOARD:
        old = new_pos
        new_pos = SNAKE_BOARD[new_pos]
        msg = f"🎲 {user.first_name}: {dice} → خانه {old} {'🐍 مار' if old < new_pos else '🪜 پله'} → {new_pos}"
    else:
        msg = f"🎲 {user.first_name}: {dice} → خانه {new_pos}"
    game[user_id] = new_pos
    save_db()
    await update.message.reply_text(msg)
    if new_pos == 30:
        add_score(user_id, 30)
        await update.message.reply_text(f"🎉 {user.first_name} برنده بازی مار و پله شد! ۳۰ امتیاز گرفت.")
        del db["snake_games"][chat_id]
        save_db()

# ================== نظرسنجی دکمه‌ای ==================
async def pollbtn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/pollbtn سوال | گزینه۱,گزینه۲,...")
    question, opts = text.split("|",1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options) < 2: return await update.message.reply_text("حداقل ۲ گزینه.")
    poll_id = str(random.randint(10000,99999))
    db["inline_polls"][poll_id] = {"question": question, "options": options, "votes": {}, "creator": str(update.effective_user.id)}
    keyboard = [[InlineKeyboardButton(f"{opt} (0)", callback_data=f"pollbtn_{poll_id}_{i}")] for i, opt in enumerate(options)]
    keyboard.append([InlineKeyboardButton("🏁 پایان نظرسنجی", callback_data=f"pollend_{poll_id}")])
    save_db()
    await update.message.reply_text(f"📊 {question}", reply_markup=InlineKeyboardMarkup(keyboard))

async def pollbtn_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data.split("_"); poll_id = data[1]; opt_idx = data[2]
    poll = db["inline_polls"].get(poll_id)
    if not poll: return await query.answer("نظرسنجی تمام شده.")
    poll["votes"][str(query.from_user.id)] = opt_idx
    keyboard = []
    for i, opt in enumerate(poll["options"]):
        count = sum(1 for v in poll["votes"].values() if v == str(i))
        keyboard.append([InlineKeyboardButton(f"{opt} ({count})", callback_data=f"pollbtn_{poll_id}_{i}")])
    keyboard.append([InlineKeyboardButton("🏁 پایان نظرسنجی", callback_data=f"pollend_{poll_id}")])
    save_db()
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def poll_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data.split("_"); poll_id = data[1]
    poll = db["inline_polls"].get(poll_id)
    if not poll: return await query.edit_message_text("نظرسنجی قبلاً تمام شده.")
    creator = poll.get("creator", "")
    if str(query.from_user.id) != creator and query.from_user.id != OWNER_ID:
        return await query.answer("فقط سازنده نظرسنجی یا مالک می‌تواند پایان دهد.", show_alert=True)
    total = len(poll["votes"])
    txt = f"📊 **نتایج نهایی:** {poll['question']}\n\n"
    for i, opt in enumerate(poll["options"]):
        count = sum(1 for v in poll["votes"].values() if v == str(i))
        pct = (count / total * 100) if total > 0 else 0
        txt += f"{opt}: {count} رأی ({pct:.1f}%)\n"
    txt += f"\n👥 کل شرکت‌کنندگان: {total}"
    await query.edit_message_text(txt)
    del db["inline_polls"][poll_id]
    save_db()

# ================== گزارش هفتگی ==================
async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    for chat_id, stats in db["weekly_stats"].items():
        if stats["messages"] == 0 and stats["mutes"] == 0 and stats["links_deleted"] == 0:
            continue
        txt = "📊 **گزارش هفتگی گروه**\n\n"
        txt += f"💬 پیام‌ها: {stats['messages']}\n"
        txt += f"🔇 سکوت‌ها: {stats['mutes']}\n"
        txt += f"🔗 لینک‌های پاک‌شده: {stats['links_deleted']}\n"
        try:
            await context.bot.send_message(int(chat_id), txt)
        except: pass
    db["weekly_stats"] = {}
    save_db()

# ================== Referral, Diary, Fal, Challenge ==================
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    ref_data = db["referrals"].get(user_id, {"count": 0})
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"
    special_link = f"https://t.me/{bot_username}?start=yasin"
    await update.message.reply_text(
        f"🔗 کد دعوت شما: `{user_id}`\n"
        f"👥 تعداد دعوت‌شده: {ref_data['count']}\n"
        f"📋 لینک دعوت:\n{link}\n\n"
        f"🎁 لینک ویژه (کد yasin): {special_link} (۵۰۰ امتیاز)",
        disable_web_page_preview=True
    )

async def diary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat_id = str(update.effective_chat.id); args = context.args
    if args:
        entry = " ".join(args)
        db["group_diaries"].setdefault(chat_id, []).append(
            {"user": update.effective_user.first_name, "text": entry, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        save_db(); await update.message.reply_text("✅ خاطره ثبت شد.")
    else:
        entries = db["group_diaries"].get(chat_id, [])
        if entries:
            txt = "📓 خاطرات گروه:\n" + "\n".join(f"{e['time']} - {e['user']}: {e['text']}" for e in entries[-10:])
            await update.message.reply_text(txt[:4000])
        else: await update.message.reply_text("هنوز خاطره‌ای ثبت نشده.")

fal_list = [
    {"poem": "یوسف گم‌گشته باز آید به کنعان غم مخور / کلبهٔ احزان شود روزی گلستان غم مخور", "desc": "نوید بازگشت عزیزان"},
    {"poem": "الا یا ایها الساقی ادر کأساً و ناولها / که عشق آسان نمود اول ولی افتاد مشکل‌ها", "desc": "مسیر عشق دشوار است"},
    {"poem": "در ازل پرتو حسنت ز تجلی دم زد / عشق پیدا شد و آتش به همه عالم زد", "desc": "آغاز خلقت از عشق"},
]
async def fal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    fal = random.choice(fal_list)
    await update.message.reply_text(f"📜 فال حافظ:\n\n{fal['poem']}\n\n🔮 تفسیر: {fal['desc']}")

daily_challenges = [
    "امروز ۳ تا تاس بنداز و مجموعش رو بگو 🎲",
    "یه جوک بگو و ببین چند لایک می‌گیری 😄",
    "با کسی که تا حالا باهاش حرف نزدی یه گفتگو کن ✨",
]
async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    await update.message.reply_text(f"🎯 چالش امروز:\n{random.choice(daily_challenges)}")

# ================== RPS ==================
RPS_OPTIONS = {"rock": "🪨 سنگ", "paper": "📄 کاغذ", "scissors": "✂️ قیچی"}
async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    keyboard = [[InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"), InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"), InlineKeyboardButton("✂️ قیچی", callback_data="rps_scissors")]]
    await update.message.reply_text("انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_choice = query.data.replace("rps_", "")
    bot_choice = random.choice(list(RPS_OPTIONS.keys()))
    result = "🤝 مساوی!" if user_choice == bot_choice else (
        "🎉 بردی!" if (user_choice == "rock" and bot_choice == "scissors") or (user_choice == "scissors" and bot_choice == "paper") or (user_choice == "paper" and bot_choice == "rock") else "😞 باختی!")
    await query.edit_message_text(f"تو: {RPS_OPTIONS[user_choice]}\nربات: {RPS_OPTIONS[bot_choice]}\n{result}")

# ================== حدس کلمه ==================
WORDS = ["شیر", "خورشید", "گل", "کتاب", "پلنگ", "دریا", "ستاره", "آسمان", "ماه", "زمین", "کوه", "آبشار", "مدرسه", "پیتزا", "برف", "بهار", "شکلات", "تلفن", "موسیقی", "فیلم"]
async def guessword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    game = db["group_games"].setdefault(str(chat.id), {})
    if game.get("word"): return await update.message.reply_text("یه بازی در حال انجامه!")
    word = random.choice(WORDS)
    hint = "🔤 " + " ".join("_" for _ in word)
    game.update({"word": word, "hint": hint, "guesses": []})
    save_db()
    keyboard = [[InlineKeyboardButton("🚫 پایان بازی", callback_data=f"endgame_{chat.id}")]]
    await update.message.reply_text(f"🎮 بازی حدس کلمه شروع شد!\n{hint} ({len(word)} حرف)\nحدس خودت رو مستقیماً تایپ کن.", reply_markup=InlineKeyboardMarkup(keyboard))

async def guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if not context.args: return await update.message.reply_text("/guess کلمه")
    guess = " ".join(context.args).strip()
    game = db["group_games"].get(str(chat.id))
    if not game or not game.get("word"): return await update.message.reply_text("بازی فعال نیست.")
    await process_guess(update.message, user, guess, game, str(chat.id))

async def end_game_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data.split("_"); chat_id = data[1]
    game = db["group_games"].get(chat_id)
    if not game or not game.get("word"): await query.edit_message_text("بازی‌ای در جریان نیست."); return
    word = game["word"]; del db["group_games"][chat_id]; save_db()
    await query.edit_message_text(f"🏁 بازی پایان یافت. کلمه «{word}» بود.")

async def process_guess(msg, user, guess, game, chat_id_str):
    if guess == game["word"]:
        add_score(str(user.id), 50)
        await msg.reply_text(f"🎉 {user.first_name} برنده شد! کلمه «{game['word']}» بود. ۵۰ امتیاز گرفت.")
        del db["group_games"][chat_id_str]
    else:
        game["guesses"].append(guess)
        word = game["word"]
        hint = " ".join(w if g == w else "_" for g, w in zip(guess, word)) if len(guess) == len(word) else game["hint"]
        game["hint"] = hint
        await msg.reply_text(f"❌ اشتباه! {hint}")
    save_db()

# ================== پت و مأموریت ==================
PET_PRICES = {"جوجه": ("🐣 جوجه", 100), "سگ": ("🐶 سگ", 200), "گربه": ("🐱 گربه", 250)}
async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    args = context.args; user_id = str(update.effective_user.id)
    if not args:
        pet = db["pets"].get(user_id)
        if pet: await update.message.reply_text(f"{pet['type']} {pet['name']} | گرسنگی: {pet['hunger']}٪")
        else: await update.message.reply_text("پتی نداری. /pet buy <نوع> <اسم>")
    elif args[0] == "buy":
        if len(args) < 3: return await update.message.reply_text("/pet buy جوجه جوجو")
        pet_type = args[1]; pet_name = args[2]
        if pet_type not in PET_PRICES: return await update.message.reply_text("نوع نامعتبر (جوجه, سگ, گربه)")
        u = get_user(user_id); price = PET_PRICES[pet_type][1]
        if u["score"] < price: return await update.message.reply_text("امتیاز کافی نداری.")
        u["score"] -= price
        db["pets"][user_id] = {"name": pet_name, "type": PET_PRICES[pet_type][0], "hunger": 0, "last_fed": datetime.now().isoformat()}
        save_db()
        await update.message.reply_text(f"🎉 {PET_PRICES[pet_type][0]} {pet_name} خریداری شد!")
    elif args[0] == "feed":
        pet = db["pets"].get(user_id)
        if not pet: return await update.message.reply_text("پتی نداری.")
        pet["hunger"] = max(0, pet["hunger"] - 20); pet["last_fed"] = datetime.now().isoformat()
        save_db()
        await update.message.reply_text(f"🍗 {pet['name']} غذا خورد! گرسنگی: {pet['hunger']}٪")
    elif args[0] == "status":
        pet = db["pets"].get(user_id)
        if not pet: return await update.message.reply_text("پتی نداری.")
        now = datetime.now(); last = datetime.fromisoformat(pet["last_fed"])
        pet["hunger"] = min(100, int((now - last).total_seconds() / 3600 * 10))
        save_db()
        await update.message.reply_text(f"{pet['type']} {pet['name']} | گرسنگی: {pet['hunger']}٪")

async def quests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    user_quests = db["quests"].setdefault(user_id, {"daily": [], "completed": []})
    if not user_quests["daily"]:
        templates = db["quests"]["templates"]
        user_quests["daily"] = random.sample(templates, min(3, len(templates)))
        save_db()
    txt = "🎯 مأموریت‌های امروز:\n"
    for q in user_quests["daily"]:
        done = q["id"] in user_quests["completed"]
        txt += f"{'✅' if done else '⬜'} {q['desc']}\n"
    await update.message.reply_text(txt)

async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    if not context.args: return await update.message.reply_text("/claim شماره")
    try: qid = int(context.args[0])
    except: return await update.message.reply_text("عدد معتبر.")
    user_quests = db["quests"].get(user_id)
    if not user_quests or not user_quests["daily"]: return await update.message.reply_text("/quests بزن.")
    if qid in user_quests["completed"]: return await update.message.reply_text("قبلاً انجام شده.")
    for q in user_quests["daily"]:
        if q["id"] == qid:
            user_quests["completed"].append(qid)
            add_score(user_id, 30); save_db()
            await update.message.reply_text("✅ مأموریت انجام شد! ۳۰ امتیاز گرفتی.")
            return
    await update.message.reply_text("شماره نامعتبر.")

# ================== قیمت ارز ==================
async def price_message(update: Update, context: ContextTypes.DEFAULT_TYPE, item: str = None):
    if not NAVASAN_API_KEY: await update.message.reply_text("کلید API نواسان تنظیم نشده."); return
    try:
        headers = {"Authorization": f"Bearer {NAVASAN_API_KEY}"}
        resp = http_req.get("https://api.navasan.tech/latest/", headers=headers, timeout=10)
        data = resp.json()
        if item == "دلار": price = data["usd"]["sell"]; txt = f"💵 دلار: {int(price):,} تومان"
        elif item == "سکه": price = data["coin"]["sell"]; txt = f"🥇 سکه: {int(price):,} تومان"
        elif item == "طلا": price = data["gold_18k"]["sell"]; txt = f"💍 طلا ۱۸: {int(price):,} تومان"
        else: return
        await update.message.reply_text(txt)
    except: await update.message.reply_text("⚠️ خطا در دریافت قیمت.")

# ================== Insta ==================
async def insta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 سرور دانلود اینستاگرام موقتاً در دسترس نیست.")

# ================== اخطار، دوز، whois، clearnotes ==================
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator","creator"] and user.id != OWNER_ID: return await update.message.reply_text("❌ فقط ادمین.")
    if not context.args or len(context.args) < 2: return await update.message.reply_text("/warn user_id دلیل")
    target_id = context.args[0]; reason = " ".join(context.args[1:])
    warnings = db["warnings"].setdefault(str(chat.id), {}).setdefault(target_id, [])
    warnings.append({"reason": reason, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_db()
    count = len(warnings)
    if count >= 3:
        target = get_user(target_id)
        if target:
            target["muted_until"] = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
            save_db()
        await update.message.reply_text(f"🚫 کاربر {target_id} ۳ اخطار گرفت و ۱۰ دقیقه بی‌صدا شد.")
    else:
        await update.message.reply_text(f"⚠️ اخطار {count}/3 به کاربر {target_id}: {reason}")

async def warns_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args: return await update.message.reply_text("/warns user_id")
    target_id = context.args[0]
    warnings = db["warnings"].get(str(update.effective_chat.id), {}).get(target_id, [])
    if warnings:
        txt = "\n".join(f"{i+1}. {w['time']} - {w['reason']}" for i, w in enumerate(warnings))
        await update.message.reply_text(f"📋 اخطارهای {target_id}:\n{txt}")
    else:
        await update.message.reply_text("این کاربر اخطاری ندارد.")

async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args: return await update.message.reply_text("/resetwarn user_id")
    target_id = context.args[0]
    chat_id = str(update.effective_chat.id)
    if chat_id in db["warnings"] and target_id in db["warnings"][chat_id]:
        del db["warnings"][chat_id][target_id]
        save_db()
        await update.message.reply_text("اخطارها پاک شد.")
    else:
        await update.message.reply_text("اخطاری برای این کاربر وجود ندارد.")

# بازی دوز
TICTACTOE_GAMES = {}
def check_winner(board):
    for i in range(0, 9, 3):
        if board[i] == board[i+1] == board[i+2] != " ": return board[i]
    for i in range(3):
        if board[i] == board[i+3] == board[i+6] != " ": return board[i]
    if board[0] == board[4] == board[8] != " ": return board[0]
    if board[2] == board[4] == board[6] != " ": return board[2]
    return None

async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    if not context.args: return await update.message.reply_text("/duel @یوزرنیم")
    opponent = context.args[0]
    try:
        member = await context.bot.get_chat_member(chat.id, update.message.entities[0].user.id)
        player2_id = member.user.id
        player2_name = member.user.first_name
    except:
        await update.message.reply_text("نفهمیدم کیو میگی. دوباره با mention تلاش کن.")
        return
    player1 = update.effective_user
    game_id = str(chat.id)
    TICTACTOE_GAMES[game_id] = {
        "board": [" "] * 9,
        "turn": player1.id,
        "p1": player1.id,
        "p2": player2_id,
        "p1_name": player1.first_name,
        "p2_name": player2_name,
        "moves": 0
    }
    await update.message.reply_text(
        f"⚔️ {player1.first_name} 🆚 {player2_name}\nنوبت {player1.first_name} (❌)",
        reply_markup=tic_tac_toe_keyboard(game_id)
    )

def tic_tac_toe_keyboard(game_id):
    board = TICTACTOE_GAMES[game_id]["board"]
    buttons = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            text = board[idx] if board[idx] != " " else str(idx+1)
            row.append(InlineKeyboardButton(text, callback_data=f"ttt_{game_id}_{idx}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def tic_tac_toe_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    game_id = data[1]
    idx = int(data[2])
    game = TICTACTOE_GAMES.get(game_id)
    if not game: return await query.edit_message_text("بازی تمام شده.")
    if query.from_user.id != game["turn"]:
        return await query.answer("نوبت تو نیست!", show_alert=True)
    if game["board"][idx] != " ":
        return await query.answer("خانه پر است!", show_alert=True)
    symbol = "❌" if game["turn"] == game["p1"] else "⭕"
    game["board"][idx] = symbol
    game["moves"] += 1
    winner = check_winner(game["board"])
    if winner:
        del TICTACTOE_GAMES[game_id]
        await query.edit_message_text(f"🏁 برنده: {winner}!", reply_markup=None)
        return
    elif game["moves"] == 9:
        del TICTACTOE_GAMES[game_id]
        await query.edit_message_text("🤝 مساوی!", reply_markup=None)
        return
    game["turn"] = game["p2"] if game["turn"] == game["p1"] else game["p1"]
    next_player = game["p1_name"] if game["turn"] == game["p1"] else game["p2_name"]
    await query.edit_message_text(
        f"⚔️ {game['p1_name']} 🆚 {game['p2_name']}\nنوبت {next_player}",
        reply_markup=tic_tac_toe_keyboard(game_id)
    )

async def whois_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args: return await update.message.reply_text("/whois @یوزرنیم یا user_id")
    target = context.args[0]
    if target.startswith("@"):
        target_user = None
        for uid, u in db["users"].items():
            if u["username"] and u["username"].lower() == target[1:].lower():
                target_user = (uid, u)
                break
        if not target_user: return await update.message.reply_text("کاربر پیدا نشد.")
    else:
        u = get_user(target)
        if not u: return await update.message.reply_text("کاربر پیدا نشد.")
        target_user = (target, u)
    uid, u = target_user
    pet = db["pets"].get(uid, None)
    items = db["user_items"].get(uid, [])
    notes = u.get("notes", [])
    txt = f"👤 {u['first_name']} (@{u['username']})\n"
    txt += f"⭐ امتیاز: {u['score']} | سطح {u['level']} | {get_user_title(u['score'], u.get('role'))}\n"
    txt += f"🐣 پت: {pet['type']} {pet['name']}" if pet else "بدون پت"
    txt += f"\n🎁 آیتم‌ها: {', '.join(items) if items else 'ندارد'}"
    txt += f"\n📒 یادداشت‌ها: {len(notes)} عدد"
    await update.message.reply_text(txt)

async def clear_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    u = get_user(user_id)
    if u:
        u["notes"] = []
        save_db()
        await update.message.reply_text("یادداشت‌ها پاک شدند.")
    else: await update.message.reply_text("ثبت‌نام نکردی.")

# ================== تایمر ==================
async def handle_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip()
    if not text.startswith("تایمر "): return False
    args = text.replace("تایمر ", "", 1).strip()
    if not args:
        await msg.reply_text("فرمت: تایمر 5m")
        return True
    try:
        unit = args[-1].lower()
        amount = int(args[:-1])
        if unit == 's': seconds = amount
        elif unit == 'm': seconds = amount * 60
        elif unit == 'h': seconds = amount * 3600
        else:
            await msg.reply_text("واحد نامعتبر (s/m/h)")
            return True
        await msg.reply_text(f"⏳ تایمر {amount}{unit} تنظیم شد.")
        await asyncio.sleep(seconds)
        await msg.reply_text("⏰ زمان تموم شد!")
    except:
        await msg.reply_text("فرمت اشتباه. مثال: تایمر 5m")
    return True

# ================== حدس شخصیت ==================
CHARACTERS = ["هیتلر", "انیشتین", "شکسپیر", "پیکاسو", "کلمبوس", "ناپلئون", "تسلا", "موتسارت", "داوینچی", "گاندی"]
async def guesswho_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    if db["guess_character"].get(str(chat.id)): return await update.message.reply_text("یه بازی حدس شخصیت در جریانه.")
    char = random.choice(CHARACTERS)
    db["guess_character"][str(chat.id)] = char
    save_db()
    await update.message.reply_text(f"🎭 بازی حدس شخصیت شروع شد! یک شخصیت تاریخی انتخاب کردم. برای حدس بزنید:\n`حدس میزنم [نام]`", parse_mode="Markdown")

async def handle_guess_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip()
    if not text.startswith("حدس میزنم "): return False
    chat_id = str(update.effective_chat.id)
    char = db["guess_character"].get(chat_id)
    if not char:
        await msg.reply_text("بازی حدس شخصیت فعال نیست. /guesswho")
        return True
    guess = text.replace("حدس میزنم ", "", 1).strip()
    if guess == char:
        add_score(str(update.effective_user.id), 30)
        await msg.reply_text(f"🎉 {update.effective_user.first_name} برنده شد! شخصیت {char} بود. ۳۰ امتیاز گرفت.")
        del db["guess_character"][chat_id]
        save_db()
    else:
        await msg.reply_text("❌ اشتباهه! دوباره تلاش کن.")
    return True

# ================== سلام خودکار ==================
async def auto_greet(context: ContextTypes.DEFAULT_TYPE):
    greetings = [
        "سلام دوستان! 🌞 امیدوارم روز خوبی داشته باشین.",
        "سلام به همه! 🤗 چطورین؟",
        "سلام! 🌸 فراموش نکنید به ربات سر بزنید.",
    ]
    msg = random.choice(greetings)
    for chat_id in db["active_chats"]:
        try: await context.bot.send_message(chat_id=chat_id, text=msg)
        except: pass

# ================== بازی‌های جدید ==================
async def coinflip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = random.choice(["شیر 🦁", "خط ⚔️"])
    await update.message.reply_text(f"🪙 سکه انداختم: {result}")

MAGIC_ANSWERS = [
    "حتماً", "بدون شک", "آره", "نه", "امکان داره", "بعداً بپرس", "مشخص نیست",
    "نشانه‌ها میگن بله", "بهتره الان نگم", "شاید", "قطعاً نه", "جواب مثبته"
]
async def magic8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args) if context.args else "سوال تو"
    answer = random.choice(MAGIC_ANSWERS)
    await update.message.reply_text(f"🎱 {question}: {answer}")

async def mathquiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(["+", "-", "*"])
    if op == "+": answer = a + b
    elif op == "-": answer = a - b
    else: answer = a * b
    db["math_games"][str(chat.id)] = {"a": a, "b": b, "op": op, "answer": answer}
    save_db()
    await update.message.reply_text(f"🧮 مسابقه ریاضی! جواب رو سریع بفرستید:\n{a} {op} {b} = ?")

# ================== استیکر، گیف ==================
async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.sticker:
        db["stickers"].append(update.message.sticker.file_id)
        save_db()

async def animation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation:
        db["animations"].append(update.message.animation.file_id)
        save_db()

# ================== زمان‌بندی ==================
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    args = context.args
    if len(args) < 2: return await update.message.reply_text("فرمت:\n/schedule YYYY-MM-DD HH:MM متن\n/schedule هر روز HH:MM متن")
    if args[0] == "هر" and args[1] == "روز":
        if len(args) < 4: return await update.message.reply_text("فرمت: /schedule هر روز 08:00 صبح بخیر")
        time_str = args[2]
        text = " ".join(args[3:])
        try:
            hour, minute = map(int, time_str.split(":"))
            context.job_queue.run_daily(send_scheduled_message, time=dt_time(hour, minute), data={"text": text, "chat_id": update.effective_chat.id}, name=str(random.randint(1000,9999)))
            await update.message.reply_text(f"✅ پیام روزانه در ساعت {time_str} تنظیم شد.")
        except Exception as e:
            await update.message.reply_text(f"خطا: {e}")
        return
    if len(args) < 3: return await update.message.reply_text("/schedule 2026-07-10 18:00 جلسه")
    date_str = args[0]
    time_str = args[1]
    text = " ".join(args[2:])
    try:
        target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        delay = (target_dt - datetime.now()).total_seconds()
        if delay < 0: return await update.message.reply_text("تاریخ گذشته است.")
        context.job_queue.run_once(send_scheduled_message, delay, data={"text": text, "chat_id": update.effective_chat.id}, name=str(random.randint(1000,9999)))
        await update.message.reply_text(f"✅ پیام برای {date_str} ساعت {time_str} زمان‌بندی شد.")
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(chat_id=job.data["chat_id"], text=f"⏰ پیام زمان‌بندی‌شده:\n{job.data['text']}")

# ================== چت ناشناس ==================
async def anon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db["anon_waiting"][user_id] = True
    save_db()
    await update.message.reply_text("📨 پیام خود را بنویسید تا به صورت ناشناس برای سازنده ارسال شود. برای لغو /cancel")

async def handle_anon_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if db["anon_waiting"].get(user_id):
        del db["anon_waiting"][user_id]
        save_db()
        text = update.message.text
        await context.bot.send_message(OWNER_ID, f"💬 پیام ناشناس:\n{text}\n(از کاربر: {user_id})")
        await update.message.reply_text("✅ پیام شما ارسال شد.")
        return True
    return False

async def anon_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    args = context.args
    if len(args) < 2: return await update.message.reply_text("/anon_reply user_id متن")
    target_id = args[0]
    reply_text = " ".join(args[1:])
    try:
        await context.bot.send_message(int(target_id), f"📩 پاسخ از طرف پشتیبانی:\n{reply_text}")
        await update.message.reply_text("✅ پاسخ ارسال شد.")
    except: await update.message.reply_text("خطا در ارسال.")

# ================== قابلیت‌های جدید ==================

# 1. ثبت تولد
async def set_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args:
        return await update.message.reply_text("فرمت: /setbirthday 1375-06-15")
    user_id = str(update.effective_user.id)
    u = get_user(user_id)
    if not u: return await update.message.reply_text("اول /start کن.")
    bday_str = context.args[0]
    try:
        parts = bday_str.split("-")
        if len(parts) != 3: raise ValueError
        year, month, day = map(int, parts)
        u["birthday"] = bday_str
        save_db()
        await update.message.reply_text(f"✅ تولد شما ثبت شد: {bday_str}")
    except:
        await update.message.reply_text("تاریخ نامعتبر. مثال: 1375-06-15")

# 2. تبریک تولد روزانه
async def birthday_check(context: ContextTypes.DEFAULT_TYPE):
    today = jdatetime.date.today()
    for uid, u in db["users"].items():
        if u.get("birthday"):
            try:
                b_parts = u["birthday"].split("-")
                b_month = int(b_parts[1])
                b_day = int(b_parts[2])
                if today.month == b_month and today.day == b_day:
                    try:
                        await context.bot.send_message(int(uid), f"🎂 تولدت مبارک {u['first_name']}! 🎉 ۵۰ امتیاز هدیه گرفتی.")
                        add_score(uid, 50)
                    except:
                        pass
            except:
                pass

# 3. گالری عکس‌ها
async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    chat_id = str(chat.id)
    group = db["group_data"].setdefault(chat_id, {"gallery": [], "locked": False, "story": None})
    photos = group.get("gallery", [])
    if not photos:
        return await update.message.reply_text("هنوز هیچ عکسی توی گالری گروه ذخیره نشده.")
    selected = random.sample(photos, min(5, len(photos)))
    for file_id in selected:
        try:
            await update.message.reply_photo(file_id)
        except:
            pass

async def cleargallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ فقط سازنده.")
    chat_id = str(update.effective_chat.id)
    group = db["group_data"].get(chat_id, {})
    group["gallery"] = []
    save_db()
    await update.message.reply_text("✅ گالری گروه پاک شد.")

async def auto_save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        chat_id = str(update.effective_chat.id)
        group = db["group_data"].setdefault(chat_id, {"gallery": [], "locked": False, "story": None})
        file_id = update.message.photo[-1].file_id
        if file_id not in group["gallery"]:
            group["gallery"].append(file_id)
            if len(group["gallery"]) > 100:
                group["gallery"] = group["gallery"][-100:]
            save_db()

# 4. قفل گروه
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator","creator"] and user.id != OWNER_ID:
        return await update.message.reply_text("❌ فقط ادمین.")
    chat_id = str(chat.id)
    group = db["group_data"].setdefault(chat_id, {"gallery": [], "locked": False, "story": None})
    group["locked"] = True
    save_db()
    await update.message.reply_text("🔒 گروه قفل شد. فقط ادمین‌ها می‌تونن پیام بدن.")

async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator","creator"] and user.id != OWNER_ID:
        return await update.message.reply_text("❌ فقط ادمین.")
    chat_id = str(chat.id)
    group = db["group_data"].setdefault(chat_id, {"gallery": [], "locked": False, "story": None})
    group["locked"] = False
    save_db()
    await update.message.reply_text("🔓 گروه را خدا ازاد کرد.")

# 5. داستان‌سرایی گروهی
STORY_STARTERS = [
    "در یک شب تاریک و طوفانی...",
    "ناگهان صدای عجیبی از زیرزمین شنیده شد...",
    "همه چیز از وقتی شروع شد که گربه شروع به حرف زدن کرد...",
    "در اعماق جنگل، یک کلبه مرموز پیدا کردیم...",
    "ساعت ۳ نیمه‌شب بود که تلفن زنگ خورد...",
]
async def story_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    chat_id = str(chat.id)
    group = db["group_data"].setdefault(chat_id, {"gallery": [], "locked": False, "story": None})
    if group.get("story"):
        return await update.message.reply_text("یه داستان در حال نوشتنه! با /story جمله‌ات رو اضافه کن یا /storyend تمومش کن.")
    starter = random.choice(STORY_STARTERS)
    group["story"] = [starter]
    save_db()
    await update.message.reply_text(f"📖 داستان گروهی شروع شد!\n{starter}\n\nبا /story جمله بعدی رو بفرستید.")

async def story_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    chat_id = str(chat.id)
    group = db["group_data"].get(chat_id, {})
    story = group.get("story")
    if not story:
        return await update.message.reply_text("داستانی شروع نشده. /storystart")
    if not context.args:
        return await update.message.reply_text("بعد از /story جمله‌ات رو بنویس.")
    sentence = " ".join(context.args)
    story.append(f"{update.effective_user.first_name}: {sentence}")
    save_db()
    await update.message.reply_text("✅ جمله‌ات به داستان اضافه شد.")

async def story_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]: return await update.message.reply_text("فقط گروه.")
    chat_id = str(chat.id)
    group = db["group_data"].get(chat_id, {})
    story = group.get("story")
    if not story:
        return await update.message.reply_text("داستانی در جریان نیست.")
    full_story = "\n".join(story)
    await send_long_message(update.effective_chat.id, f"📖 **داستان گروهی به پایان رسید:**\n\n{full_story}", context.bot)
    group["story"] = None
    save_db()

# ================== قابلیت‌های جدید ==================

# 1. سیستم تیکت
async def ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db["ticket_waiting"][user_id] = True
    save_db()
    await update.message.reply_text("🎫 لطفاً پیام خود را بنویسید تا به پشتیبانی ارسال شود. برای لغو /cancel")

async def handle_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if db["ticket_waiting"].get(user_id):
        del db["ticket_waiting"][user_id]
        save_db()
        text = update.message.text
        await context.bot.send_message(OWNER_ID, f"🎫 تیکت از کاربر {user_id}:\n{text}")
        await update.message.reply_text("✅ تیکت شما ثبت شد. پشتیبانی به زودی پاسخ می‌دهد.")
        return True
    return False

async def ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    args = context.args
    if len(args) < 2: return await update.message.reply_text("/ticketreply user_id متن")
    target_id = args[0]
    reply_text = " ".join(args[1:])
    try:
        await context.bot.send_message(int(target_id), f"📩 پاسخ پشتیبانی:\n{reply_text}")
        await update.message.reply_text("✅ پاسخ ارسال شد.")
    except: await update.message.reply_text("خطا در ارسال.")

# 2. بازی میلیونر
MILLIONAIRE_QUESTIONS = [
    {"q": "پایتخت ایران؟", "opts": ["تهران", "اصفهان", "شیراز", "تبریز"], "ans": 0},
    {"q": "۲+۲ چند می‌شود؟", "opts": ["۳", "۴", "۵", "۶"], "ans": 1},
    {"q": "بزرگترین اقیانوس جهان؟", "opts": ["اطلس", "هند", "آرام", "منجمد شمالی"], "ans": 2},
    {"q": "رنگ خورشید؟", "opts": ["آبی", "سبز", "زرد", "قرمز"], "ans": 2},
    {"q": "تعداد استان‌های ایران؟", "opts": ["۳۰", "۳۱", "۳۲", "۳۳"], "ans": 1},
]
async def millionaire_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    questions = random.sample(MILLIONAIRE_QUESTIONS, min(5, len(MILLIONAIRE_QUESTIONS)))
    db["millionaire_games"][user_id] = {"questions": questions, "current": 0, "score": 0}
    save_db()
    await ask_millionaire_question(update, context, user_id)

async def ask_millionaire_question(update, context, user_id):
    game = db["millionaire_games"].get(user_id)
    if not game: return
    idx = game["current"]
    if idx >= len(game["questions"]):
        await update.message.reply_text(f"🎉 بازی تمام شد! امتیاز نهایی: {game['score']}")
        del db["millionaire_games"][user_id]
        save_db()
        return
    q = game["questions"][idx]
    keyboard = []
    for i, opt in enumerate(q["opts"]):
        keyboard.append([InlineKeyboardButton(opt, callback_data=f"million_{i}")])
    await update.message.reply_text(f"💰 سوال {idx+1}: {q['q']}", reply_markup=InlineKeyboardMarkup(keyboard))

async def millionaire_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = str(query.from_user.id)
    game = db["millionaire_games"].get(user_id)
    if not game: return await query.edit_message_text("بازی تمام شده.")
    ans = int(query.data.split("_")[1])
    q = game["questions"][game["current"]]
    if ans == q["ans"]:
        game["score"] += 10
        await query.edit_message_text("✅ درست!")
    else:
        await query.edit_message_text(f"❌ اشتباه! جواب: {q['opts'][q['ans']]}")
    game["current"] += 1
    save_db()
    await ask_millionaire_question(update, context, user_id)

# 3. معرفی دوستان با جزئیات
async def myreferrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    ref_data = db["referrals"].get(user_id, {})
    invited = ref_data.get("invited", [])
    if not invited:
        await update.message.reply_text("هنوز کسی رو دعوت نکردی.")
        return
    txt = "👥 دوستانی که دعوت کردی:\n"
    for uid in invited[:20]:
        u = get_user(uid)
        name = u["first_name"] if u else "کاربر ناشناس"
        txt += f"• {name} (`{uid}`)\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# 4. مدیریت فایل
async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name or "بدون نام"
        db["files"].append({"file_id": file_id, "file_name": file_name, "type": "document", "uploader": str(update.effective_user.id)})
        save_db()
        await msg.reply_text(f"📁 فایل «{file_name}» ذخیره شد.")
    elif msg.video:
        file_id = msg.video.file_id
        file_name = msg.video.file_name or "ویدیو"
        db["files"].append({"file_id": file_id, "file_name": file_name, "type": "video", "uploader": str(update.effective_user.id)})
        save_db()
        await msg.reply_text("📹 ویدیو ذخیره شد.")
    elif msg.audio:
        file_id = msg.audio.file_id
        file_name = msg.audio.file_name or "صدا"
        db["files"].append({"file_id": file_id, "file_name": file_name, "type": "audio", "uploader": str(update.effective_user.id)})
        save_db()
        await msg.reply_text("🎵 صوت ذخیره شد.")

async def files_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = db["files"]
    if not files:
        await update.message.reply_text("هیچ فایلی ذخیره نشده.")
        return
    txt = "📁 فایل‌های آپلود شده:\n"
    for i, f in enumerate(files[-20:], 1):
        txt += f"{i}. {f['file_name']} ({f['type']})\n"
    await update.message.reply_text(txt)
    await update.message.reply_text("برای دریافت فایل، شماره آن را با /getfile بفرست.")

async def getfile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/getfile شماره")
        return
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["files"]):
            f = db["files"][idx]
            if f["type"] == "document":
                await update.message.reply_document(f["file_id"])
            elif f["type"] == "video":
                await update.message.reply_video(f["file_id"])
            elif f["type"] == "audio":
                await update.message.reply_audio(f["file_id"])
        else:
            await update.message.reply_text("شماره نامعتبر.")
    except:
        await update.message.reply_text("عدد وارد کن.")

# 5. واکنش طنز
FUNNY_REACTIONS = [
    "واکنشت رو دیدم! 😏",
    "آفرین، یه لایک برای تو!",
    "مرسی از واکنشت! 🤪",
    "با این واکنش خوشم اومد!",
    "😎👌",
]

async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message_reaction:
            await update.message.reply_text(random.choice(FUNNY_REACTIONS))
    except:
        pass

# ================== مدیریت پیام‌ها (اصلی) ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    msg = update.message; chat = update.effective_chat; user = update.effective_user
    user_id = str(user.id); text = msg.text or msg.caption or ""

    if chat.id not in db["active_chats"]: db["active_chats"].append(chat.id); save_db()
    register_user(user_id, user.username or "", user.first_name or "")
    u = get_user(user_id)
    if u and u["blocked"]: return
    if is_muted(user_id):
        try: await msg.delete()
        except: pass
        return

    log_action(user_id, "message", text[:50])

    # آمار هفتگی
    chat_id = str(chat.id)
    db["weekly_stats"].setdefault(chat_id, {"messages": 0, "mutes": 0, "links_deleted": 0})
    db["weekly_stats"][chat_id]["messages"] += 1

    # قفل گروه
    if chat.type in ["group","supergroup"]:
        group = db["group_data"].get(chat_id, {})
        if group.get("locked", False):
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ["administrator","creator"] and user.id != OWNER_ID:
                try: await msg.delete()
                except: pass
                return

    await auto_save_photo(update, context)
    if await handle_anon_message(update, context): return
    if await handle_ticket_message(update, context): return

    # ذخیره فایل‌های ارسالی
    if msg.document or msg.video or msg.audio:
        await file_handler(update, context)
        return

    # ضد لینک
    if chat.type in ["group","supergroup"] and re.search(r'https?://', text):
        await msg.reply_text("❌ عدالت برای همه یکسان است")
        try: await msg.delete()
        except: pass
        db["weekly_stats"][chat_id]["links_deleted"] += 1
        save_db()
        return

    # ضد اسپم
    if chat.type in ["group","supergroup"] and is_spam(user_id):
        try: await msg.delete(); await msg.reply_text("❌ اسپم نکنید.")
        except: pass
        return

    # فیلتر کلمات
    if chat.type in ["group","supergroup"]:
        for bw in db["bad_words"]:
            if bw in text.lower():
                try: await msg.delete(); await msg.reply_text("⛔ پیام حذف شد.")
                except: pass
                return

    add_score(user_id)

    # مسابقه ریاضی
    if chat.type in ["group","supergroup"] and text.strip().isdigit():
        game = db["math_games"].get(chat_id)
        if game:
            try:
                guess = int(text.strip())
                if guess == game["answer"]:
                    add_score(user_id, 20)
                    await msg.reply_text(f"🎉 {user.first_name} درست گفت! جواب {game['answer']} بود. ۲۰ امتیاز گرفتی.")
                    del db["math_games"][chat_id]; save_db()
                    return
                else: await msg.reply_text("❌ اشتباهه."); return
            except: pass

    # حدس کلمه
    if chat.type in ["group","supergroup"] and not text.startswith("/"):
        game = db["group_games"].get(chat_id)
        if game and game.get("word"):
            await process_guess(msg, user, text.strip(), game, chat_id)
            return

    # حدس شخصیت
    if await handle_guess_character(update, context): return

    # تایمر
    if await handle_timer(update, context): return

    # شیر خط و توپ جادویی
    if text == "شیر یا خط": await coinflip(update, context); return
    if text.startswith("توپ جادویی "):
        answer = random.choice(MAGIC_ANSWERS); await msg.reply_text(f"🎱 {answer}"); return
    if text == "توپ جادویی": await msg.reply_text("🎱 سوالت رو بعد از «توپ جادویی» بنویس."); return

    # پشتیبانی
    if text == "پشتیبانی": await msg.reply_text(f"📞 ارتباط با سازنده:\n{ADMIN_USERNAME}"); return

    # کلمات یادگرفته‌شده
    for trigger, response in db["learned"].items():
        if trigger.lower() in text.lower(): await msg.reply_text(response); return

    # جک
    if text in ["جک","جوک","جوک بگو"]:
        if db["jokes"]:
            joke = random.choice(db["jokes"])
            keyboard = [[InlineKeyboardButton("👍", callback_data="like"), InlineKeyboardButton("👎", callback_data="dislike")]]
            await msg.reply_text(joke, reply_markup=InlineKeyboardMarkup(keyboard))
        else: await msg.reply_text("هنوز جکی یادم ندادی!")
        return

    # نقل‌قول
    if text in ["نقل‌قول","جمله"]:
        if db["quotes"]: await msg.reply_text(random.choice(db["quotes"]))
        else: await msg.reply_text("هنوز نقل‌قولی ثبت نشده.")
        return

    # استیکر/گیف
    if text == "استیکر":
        if db["stickers"]: await msg.reply_sticker(sticker=random.choice(db["stickers"]))
        else: await msg.reply_text("استیکری نفرستادی.")
        return
    if text == "گیف":
        if db["animations"]: await msg.reply_animation(animation=random.choice(db["animations"]))
        else: await msg.reply_text("گیفی نفرستادی.")
        return

    # ساعت / تاریخ
    if text == "ساعت": await msg.reply_text(f"⏰ {datetime.now().strftime('%H:%M:%S')}"); return
    if text in ["تاریخ","امروز"]:
        now = jdatetime.datetime.now()
        await msg.reply_text(f"📅 {now.strftime('%Y/%m/%d')} - {now.strftime('%A')}"); return

    # قیمت‌ها
    if text in ["دلار","سکه","طلا"]: await price_message(update, context, text); return

    # تالار
    if text == "تالار":
        top = get_top_users(5)
        if top:
            txt = "🏆 تالار افتخارات:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i,r in enumerate(top))
            sent = await msg.reply_text(txt)
            try: await sent.pin(disable_notification=True)
            except: pass
        return

    # امتیاز
    if text == "امتیاز":
        await msg.reply_text(f"🌟 {u['score']} امتیاز | سطح {u['level']} | {get_user_title(u['score'], u.get('role'))}")
        return
    if text == "تاپ":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']}) {get_user_title(r[1]['score'], r[1].get('role'))}" for i,r in enumerate(top)) if top else "خالی."
        await msg.reply_text(txt)
        return

    # یادداشت
    if text.startswith("یادداشت:"):
        note = text.replace("یادداشت:","",1).strip()
        if note: u["notes"].append({"text": note, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}); save_db(); await msg.reply_text("✅ ذخیره شد.")
        return
    if text == "یادداشت‌ها":
        notes = u.get("notes",[])
        if notes: await msg.reply_text("📒 یادداشت‌ها:\n" + "\n".join(f"• {n['time']}: {n['text']}" for n in notes[-10:]))
        else: await msg.reply_text("یادداشتی نداری.")
        return

    # منو
    if text == "منو": await msg.reply_text("📋 منوی اصلی:", reply_markup=get_main_menu_keyboard(update.effective_user.id)); return

    # تاس/دارت
    if text == "تاس": await msg.reply_dice(emoji="🎲"); return
    if text == "دارت": await msg.reply_dice(emoji="🎯"); return

    # قرعه‌کشی
    if text == "قرعه‌کشی" and chat.type in ["group","supergroup"]:
        try:
            members = [m.user.id async for m in context.bot.get_chat_members(chat.id) if not m.user.is_bot]
            winner = random.choice(members)
            await msg.reply_text(f"🎉 برنده: <a href='tg://user?id={winner}'>{winner}</a>", parse_mode="HTML")
        except: pass
        return

    if msg.photo: await msg.reply_text("📸 عکس دریافت شد."); return

# ================== دکمه‌ها ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; user_id = str(query.from_user.id)

    if data.startswith("ttt_"): await tic_tac_toe_button(update, context); return
    if data.startswith("pollbtn_"): await pollbtn_vote(update, context); return
    if data.startswith("pollend_"): await poll_end(update, context); return
    if data.startswith("million_"): await millionaire_answer(update, context); return

    # منوها
    if data == "menu_main": await query.edit_message_text("📋 منوی اصلی:", reply_markup=get_main_menu_keyboard(query.from_user.id))
    elif data == "menu_games": await query.edit_message_text("🎮 بازی‌ها:", reply_markup=get_games_keyboard())
    elif data == "menu_tools": await query.edit_message_text("🛠 ابزارها:", reply_markup=get_tools_keyboard())
    elif data == "menu_profile": await query.edit_message_text("👤 پروفایل:", reply_markup=get_profile_keyboard())
    elif data == "menu_group": await query.edit_message_text("👥 امکانات گروهی:", reply_markup=get_group_keyboard())
    elif data == "menu_files": await query.edit_message_text("📁 فایل‌ها: /files", reply_markup=get_main_menu_keyboard(query.from_user.id))
    elif data == "ticket_start": await ticket_start(update, context)
    elif data == "menu_admin":
        if query.from_user.id != OWNER_ID: await query.answer("فقط سازنده!", show_alert=True); return
        await query.edit_message_text("👑 پنل ادمین:", reply_markup=get_admin_keyboard())

    # راهنماهای ورودی
    elif data == "rps_menu": await query.message.reply_text("/rps")
    elif data == "magic8_menu": await query.message.reply_text("توپ جادویی سوال")
    elif data == "guessword_menu": await query.message.reply_text("/guessword (توی گروه)")
    elif data == "guesswho_menu": await query.message.reply_text("/guesswho (توی گروه)")
    elif data == "duel_menu": await query.message.reply_text("/duel @یوزرنیم")
    elif data == "snake_menu": await query.message.reply_text("برای مار و پله: /snake (گروه)")
    elif data == "roll_menu": await query.message.reply_text("برای چرخ شانس: /roll")
    elif data == "millionaire_menu": await query.message.reply_text("برای میلیونر: /millionaire")
    elif data == "pet_menu": await query.message.reply_text("/pet buy|feed|status")
    elif data == "quests_menu": await query.message.reply_text("/quests و /claim")
    elif data == "poll_menu": await query.message.reply_text("/poll سوال | گزینه‌ها")
    elif data == "pollbtn_menu": await query.message.reply_text("/pollbtn سوال | گزینه‌ها")
    elif data == "remind_menu": await query.message.reply_text("/remind 10m پیام")
    elif data == "timer_menu": await query.message.reply_text("تایمر 5m")
    elif data == "note_menu": await query.message.reply_text("یادداشت: متن")
    elif data == "fal_menu": await query.message.reply_text("/fal")
    elif data == "challenge_menu": await query.message.reply_text("/challenge")
    elif data == "referral_menu": await query.message.reply_text("/referral")
    elif data == "birthday_menu": await query.message.reply_text("/setbirthday 1375-06-15")
    elif data == "whois_menu": await query.message.reply_text("/whois @یوزرنیم")
    elif data == "myreferrals": await query.message.reply_text("/myreferrals")
    elif data == "mute_menu": await query.message.reply_text("/mute user_id دقیقه")
    elif data == "warn_menu": await query.message.reply_text("/warn user_id دلیل")
    elif data == "warns_menu": await query.message.reply_text("/warns user_id")
    elif data == "resetwarn_menu": await query.message.reply_text("/resetwarn user_id")
    elif data == "lock_menu": await query.message.reply_text("/lock (ادمین)")
    elif data == "unlock_menu": await query.message.reply_text("/unlock (ادمین)")
    elif data == "story_menu": await query.message.reply_text("/storystart")
    elif data == "diary_menu": await query.message.reply_text("/diary")
    elif data == "hall_menu": await query.message.reply_text("تالار")
    elif data == "gallery_menu": await query.message.reply_text("/gallery")
    elif data == "role_menu": await query.message.reply_text("/role user_id نقش")
    elif data == "admin_stats": await query.message.reply_text("/admin stats")
    elif data == "admin_broadcast": await query.message.reply_text("/admin broadcast متن")
    elif data == "admin_block": await query.message.reply_text("/admin block user_id")
    elif data == "admin_unblock": await query.message.reply_text("/admin unblock user_id")
    elif data == "admin_badword": await query.message.reply_text("/admin badword add/remove کلمه")
    elif data == "admin_logs": await query.message.reply_text("/admin logs")
    elif data == "learn_menu": await query.message.reply_text("/learn کلمه | پاسخ")
    elif data == "unlearn_menu": await query.message.reply_text("/unlearn کلمه")
    elif data == "addjoke_menu": await query.message.reply_text("/addjoke متن")
    elif data == "deljoke_menu": await query.message.reply_text("/deljoke شماره")
    elif data == "addquote_menu": await query.message.reply_text("/addquote متن")
    elif data == "delquote_menu": await query.message.reply_text("/delquote شماره")
    elif data == "jokes_list": await query.message.reply_text("/jokes")
    elif data == "quotes_list": await query.message.reply_text("/quotes")
    elif data == "shop_manage": await query.message.reply_text("/additem, /removeitem, /editprice")
    elif data == "schedule_menu": await query.message.reply_text("/schedule")
    elif data == "dailyreward_btn": await query.message.reply_text("/dailyreward")
    elif data == "bot_toggle": await query.message.reply_text("/bot on / off")

    # دکمه‌های عملی
    elif data == "coinflip":
        result = random.choice(["شیر 🦁", "خط ⚔️"])
        await query.message.reply_text(f"🪙 سکه انداختم: {result}")
    elif data == "mathquiz":
        if query.message.chat.type not in ["group","supergroup"]: await query.message.reply_text("فقط توی گروه.")
        else:
            a = random.randint(1, 20); b = random.randint(1, 20)
            op = random.choice(["+", "-", "*"])
            answer = a + b if op == "+" else a - b if op == "-" else a * b
            db["math_games"][str(query.message.chat.id)] = {"a": a, "b": b, "op": op, "answer": answer}
            save_db()
            await query.message.reply_text(f"🧮 مسابقه ریاضی! جواب رو سریع بفرستید:\n{a} {op} {b} = ?")
    elif data == "today":
        now = jdatetime.datetime.now()
        await query.message.reply_text(f"📅 {now.strftime('%Y/%m/%d')} - {now.strftime('%A')}")
    elif data == "clearnotes":
        u = get_user(user_id)
        if u: u["notes"] = []; save_db(); await query.message.reply_text("یادداشت‌ها پاک شدند.")
    elif data == "pet_status":
        pet = db["pets"].get(user_id)
        if pet: await query.message.reply_text(f"{pet['type']} {pet['name']} | گرسنگی: {pet['hunger']}٪")
        else: await query.message.reply_text("پتی نداری.")
    elif data == "items_menu":
        items = db["user_items"].get(user_id, [])
        if items: await query.message.reply_text("🎁 آیتم‌ها:\n" + "\n".join(f"• {i}" for i in items))
        else: await query.message.reply_text("هنوز چیزی نخریدی.")
    elif data == "anon_chat":
        db["anon_waiting"][user_id] = True; save_db()
        await query.message.reply_text("📨 پیام خود را بنویسید (ناشناس). برای لغو /cancel")
    elif data == "menu_shop":
        shop = db["shop"]
        if not shop: await query.message.reply_text("فروشگاه خالیه.")
        else:
            txt = "🛍 فروشگاه:\n"
            for i, item in enumerate(shop, 1):
                stock = item.get("stock", "نامحدود")
                txt += f"{i}. {item['name']} - 💰 {item['price']} | 📦 {stock}\n"
            await query.message.reply_text(txt)
    elif data == "dice": await query.message.reply_dice(emoji="🎲")
    elif data == "dart": await query.message.reply_dice(emoji="🎯")
    elif data == "creator": await query.message.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif data == "score":
        u = get_user(user_id)
        await query.message.reply_text(f"🌟 {u['score']} امتیاز | {get_user_title(u['score'], u.get('role'))}" if u else "نیستی.")
    elif data == "top":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']}) {get_user_title(r[1]['score'], r[1].get('role'))}" for i,r in enumerate(top)) if top else "خالی."
        await query.message.reply_text(txt)
    elif data == "shownotes":
        u = get_user(user_id)
        notes = u.get("notes",[]) if u else []
        if notes: await query.message.reply_text("📒 یادداشت‌ها:\n" + "\n".join(f"• {n['time']}: {n['text']}" for n in notes[-10:]))
        else: await query.message.reply_text("یادداشتی نداری.")
    elif data in ("price_dollar","price_coin","price_gold"):
        item = {"price_dollar":"دلار","price_coin":"سکه","price_gold":"طلا"}[data]
        await price_message(update, context, item)
    elif data.startswith("rps_"): await handle_rps(update, context)
    elif data in ("like","dislike"): await query.answer(f"شما {'👍' if data=='like' else '👎'} دادید")
    elif data == "help": await query.message.reply_text(f"📖 راهنما: {CHANNEL_LINK}", disable_web_page_preview=True)

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot: await update.message.reply_text(f"خوش آمدی {member.first_name} 🌹")

# ================== اجرا ==================
def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    app.job_queue.run_repeating(auto_greet, interval=21600, first=10)
    app.job_queue.run_daily(birthday_check, time=dt_time(7, 0))
    app.job_queue.run_daily(weekly_report, time=dt_time(18, 0), days=(6,))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("bot", bot_toggle))
    app.add_handler(CommandHandler("dailyreward", daily_reward))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("poll", poll_command))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("learn", learn_command))
    app.add_handler(CommandHandler("unlearn", unlearn_command))
    app.add_handler(CommandHandler("addjoke", addjoke_command))
    app.add_handler(CommandHandler("deljoke", deljoke_command))
    app.add_handler(CommandHandler("jokes", list_jokes_command))
    app.add_handler(CommandHandler("addquote", addquote_command))
    app.add_handler(CommandHandler("delquote", delquote_command))
    app.add_handler(CommandHandler("quotes", list_quotes_command))
    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("items", my_items_command))
    app.add_handler(CommandHandler("additem", additem_command))
    app.add_handler(CommandHandler("removeitem", removeitem_command))
    app.add_handler(CommandHandler("editprice", editprice_command))
    app.add_handler(CommandHandler("role", role_command))
    app.add_handler(CommandHandler("unrole", unrole_command))
    app.add_handler(CommandHandler("roll", roll_command))
    app.add_handler(CommandHandler("snake", snake_command))
    app.add_handler(CommandHandler("dice", snake_dice))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("myreferrals", myreferrals_command))
    app.add_handler(CommandHandler("diary", diary_command))
    app.add_handler(CommandHandler("fal", fal_command))
    app.add_handler(CommandHandler("challenge", challenge_command))
    app.add_handler(CommandHandler("rps", rps_command))
    app.add_handler(CommandHandler("guessword", guessword_command))
    app.add_handler(CommandHandler("guess", guess_command))
    app.add_handler(CommandHandler("pet", pet_command))
    app.add_handler(CommandHandler("quests", quests_command))
    app.add_handler(CommandHandler("claim", claim_command))
    app.add_handler(CommandHandler("pollbtn", pollbtn_command))
    app.add_handler(CommandHandler("insta", insta_command))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("warns", warns_list))
    app.add_handler(CommandHandler("resetwarn", reset_warns))
    app.add_handler(CommandHandler("duel", duel_command))
    app.add_handler(CommandHandler("whois", whois_command))
    app.add_handler(CommandHandler("clearnotes", clear_notes))
    app.add_handler(CommandHandler("guesswho", guesswho_command))
    app.add_handler(CommandHandler("mathquiz", mathquiz_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("anon", anon_command))
    app.add_handler(CommandHandler("anon_reply", anon_reply_command))
    app.add_handler(CommandHandler("ticket", ticket_start))
    app.add_handler(CommandHandler("ticketreply", ticket_reply))
    app.add_handler(CommandHandler("millionaire", millionaire_command))
    app.add_handler(CommandHandler("files", files_list))
    app.add_handler(CommandHandler("getfile", getfile_command))
    app.add_handler(CommandHandler("setbirthday", set_birthday))
    app.add_handler(CommandHandler("gallery", gallery_command))
    app.add_handler(CommandHandler("cleargallery", cleargallery_command))
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("unlock", unlock_command))
    app.add_handler(CommandHandler("storystart", story_start))
    app.add_handler(CommandHandler("story", story_add))
    app.add_handler(CommandHandler("storyend", story_end))
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    app.add_handler(MessageHandler(filters.ANIMATION, animation_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO, file_handler))
    #app.add_handler(MessageHandler(filters.Reaction, handle_reaction))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات نهایی کامل اجرا شد.")
    app.run_polling()

if __name__ == "__main__":
    main()

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
db.setdefault("group_diaries", {})
db.setdefault("referrals", {})
db.setdefault("shop", [])              # هر آیتم: {"name":..., "price":..., "stock":...}
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
db.setdefault("used_yasin", [])
db.setdefault("group_data", {})        # gallery, locked, story
db.setdefault("daily_rolls", {})       # کاربرانی که امروز چرخ شانس زده‌اند
db.setdefault("snake_games", {})       # بازی مار و پله
db.setdefault("weekly_stats", {})      # آمار هفتگی: {chat_id: {"messages":..., "mutes":..., "links_deleted":...}}

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
        await update.message.reply_text("⛔ ربات به دستور سازنده خاموش است.")
        return True
    return False

# ================== تابع کمکی ارسال پیام بلند ==================
async def send_long_message(chat_id, text, bot, max_len=4000):
    for i in range(0, len(text), max_len):
        await bot.send_message(chat_id=chat_id, text=text[i:i+max_len])

# ================== منوهای شیشه‌ای (گسترده) ==================
def get_main_menu_keyboard(user_id: int = None):
    keyboard = [
        [InlineKeyboardButton("🎮 بازی‌ها", callback_data="menu_games")],
        [InlineKeyboardButton("🛠 ابزارها", callback_data="menu_tools")],
        [InlineKeyboardButton("👤 پروفایل", callback_data="menu_profile")],
        [InlineKeyboardButton("👥 گروه", callback_data="menu_group")],
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
        [InlineKeyboardButton("🐣 پت", callback_data="pet_status"), InlineKeyboardButton("🎂 تولد", callback_data="birthday_menu")],
        [InlineKeyboardButton("🔗 کد دعوت", callback_data="referral_menu"), InlineKeyboardButton("👤 whois", callback_data="whois_menu")],
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

# ================== دستور start (راهنمای کوتاه) ==================
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
        f"🤖 **به Diminol-bot خوش اومدی!**\nساخته‌ی یاسین چنگیزی ❤️\n\n"
        f"📖 برای دریافت راهنمای کامل دستورات به کانال زیر مراجعه کنید:\n{CHANNEL_LINK}\n\n"
        f"یا بنویس `منو` تا دکمه‌های شیشه‌ای را ببینی.",
        reply_markup=get_main_menu_keyboard(update.effective_user.id),
        disable_web_page_preview=True
    )

# ================== پنل ادمین (با اعلان مسدودی) ==================
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
    # آمار هفتگی
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
    txt = "📋 لیست جُک‌ها:\n" + "\n".join(f"{i+1}. {j}" for i,j in enumerate(jokes))
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

# ================== فروشگاه (با موجودی) ==================
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
    name = " ".join(args[:-1]) if len(args) > 2 else args[0]
    try:
        price = int(args[-1])
        stock = None
        if len(args) > 2:
            stock = int(args[-2])
            name = " ".join(args[:-2])
        else:
            name = " ".join(args[:-1])
    except: return await update.message.reply_text("قیمت باید عدد باشه.")
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
ROLL_PRIZES = [10, 20, 30, 50, 100, 0, 5, 15, 25, 0]  # ترکیب جوایز

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
SNAKE_BOARD = {
    3: 11, 8: 17, 16: 4, 21: 9, 27: 1   # مارها و پله‌ها
}

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

# ================== نظرسنجی دکمه‌ای (با پایان) ==================
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
    # ریست آمار
    db["weekly_stats"] = {}
    save_db()

# ================== مدیریت پیام‌ها (آمار هفتگی) ==================
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

    # ضد لینک
    if chat.type in ["group","supergroup"] and re.search(r'https?://', text):
        await msg.reply_text("❌ لینک ممنوع است.")
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

    # منوها
    if data == "menu_main": await query.edit_message_text("📋 منوی اصلی:", reply_markup=get_main_menu_keyboard(query.from_user.id))
    elif data == "menu_games": await query.edit_message_text("🎮 بازی‌ها:", reply_markup=get_games_keyboard())
    elif data == "menu_tools": await query.edit_message_text("🛠 ابزارها:", reply_markup=get_tools_keyboard())
    elif data == "menu_profile": await query.edit_message_text("👤 پروفایل:", reply_markup=get_profile_keyboard())
    elif data == "menu_group": await query.edit_message_text("👥 امکانات گروهی:", reply_markup=get_group_keyboard())
    elif data == "menu_admin":
        if query.from_user.id != OWNER_ID: await query.answer("فقط سازنده!", show_alert=True); return
        await query.edit_message_text("👑 پنل ادمین:", reply_markup=get_admin_keyboard())

    # راهنماها
    elif data == "rps_menu": await query.message.reply_text("/rps")
    elif data == "magic8_menu": await query.message.reply_text("توپ جادویی سوال")
    elif data == "guessword_menu": await query.message.reply_text("/guessword (توی گروه)")
    elif data == "guesswho_menu": await query.message.reply_text("/guesswho (توی گروه)")
    elif data == "duel_menu": await query.message.reply_text("/duel @یوزرنیم")
    elif data == "snake_menu": await query.message.reply_text("برای مار و پله: /snake (گروه)")
    elif data == "roll_menu": await query.message.reply_text("برای چرخ شانس: /roll")
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

# ================== توابع قدیمی (RPS, حدس کلمه, پت, مأموریت, قیمت, Insta, اخطار, دوز, whois, clearnotes, تایمر, حدس شخصیت, سلام خودکار, بازی‌ها, استیکر, گیف, زمان‌بندی, چت ناشناس, تولد, گالری, قفل, داستان) بدون تغییر از نسخه قبلی ==================
# (جهت خلاصه‌سازی حذف شده‌اند؛ در فایل اصلی کامل وجود دارند)

# ================== اجرا ==================
def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    app.job_queue.run_repeating(auto_greet, interval=21600, first=10)
    app.job_queue.run_daily(birthday_check, time=dt_time(7, 0))
    app.job_queue.run_daily(weekly_report, time=dt_time(18, 0), days=(6,))  # جمعه‌ها ساعت ۱۸

    # ثبت همه هندلرها (قدیم + جدید)
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات با همه ارتقاهای جدید اجرا شد.")
    app.run_polling()

if __name__ == "__main__":
    main()

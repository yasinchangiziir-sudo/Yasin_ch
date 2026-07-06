import os, json, random, re, asyncio, threading
from datetime import datetime, timedelta
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
db.setdefault("learned", {})
db.setdefault("stickers", [])
db.setdefault("animations", [])
db.setdefault("group_diaries", {})
db.setdefault("referrals", {})
db.setdefault("shop", [
    {"name": "🏅 مدال طلا", "price": 100},
    {"name": "🥈 مدال نقره", "price": 50},
    {"name": "💎 نشان الماس", "price": 200}
])
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
            "notes": [], "muted_until": None
        }
        if referrer_id and referrer_id in db["users"] and referrer_id != user_id:
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

# ================== منوهای شیشه‌ای ==================
def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 بازی‌ها", callback_data="menu_games")],
        [InlineKeyboardButton("🛠 ابزارها", callback_data="menu_tools")],
        [InlineKeyboardButton("👤 پروفایل", callback_data="menu_profile")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
    ])
def get_games_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 تاس", callback_data="dice"), InlineKeyboardButton("🎯 دارت", callback_data="dart")],
        [InlineKeyboardButton("✂️ سنگ کاغذ قیچی", callback_data="rps_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])
def get_tools_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 دلار", callback_data="price_dollar"), InlineKeyboardButton("🥇 سکه", callback_data="price_coin"), InlineKeyboardButton("💍 طلا", callback_data="price_gold")],
        [InlineKeyboardButton("📋 نظرسنجی", callback_data="menu_pollbtn"), InlineKeyboardButton("⏰ یادآوری", callback_data="menu_remind")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])
def get_profile_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ امتیاز", callback_data="score"), InlineKeyboardButton("🏆 تاپ", callback_data="top")],
        [InlineKeyboardButton("📒 یادداشت‌ها", callback_data="shownotes"), InlineKeyboardButton("🛍 فروشگاه", callback_data="menu_shop")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")],
    ])

# ================== دستور start ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = context.args[0] if context.args else None
    register_user(str(user.id), user.username or "", user.first_name or "", referrer_id)
    welcome_text = """
🤖 **به Diminol-bot خوش اومدی!**
ساخته‌ی یاسین چنگیزی ❤️

📌 **راهنمای کامل دستورات:**

🎮 **سرگرمی و بازی:**
• `/rps` – بازی سنگ-کاغذ-قیچی
• `/fal` – فال حافظ با تفسیر
• `/challenge` – دریافت چالش روزانه
• `/guessword` – شروع بازی حدس کلمه (گروه)
• `/pet` – خرید، غذا دادن و وضعیت پت مجازی
• `/quests` – مشاهدهٔ مأموریت‌های روزانه
• `/claim شماره` – تحویل مأموریت و دریافت جایزه
• `تاس` یا `دارت` – انداختن تاس یا دارت
• `جک` / `جوک` / `جوک بگو` – یک جوک تصادفی
• `استیکر` – دریافت یک استیکر تصادفی از آرشیو
• `گیف` – دریافت یک گیف تصادفی از آرشیو
• `قرعه‌کشی` – انتخاب تصادفی یک عضو (گروه)
• `/duel @یوزرنیم` – بازی دوز (گروه)
• `/guesswho` – بازی حدس شخصیت (گروه)

🛠 **ابزارهای کاربردی:**
• `دلار` / `سکه` / `طلا` – قیمت لحظه‌ای
• `ساعت` – نمایش ساعت فعلی
• `تاریخ` / `امروز` – تاریخ شمسی
• `نقل‌قول` / `جمله` – یک جملهٔ زیبا
• `/poll سوال | گزینه‌ها` – نظرسنجی تلگرامی
• `/pollbtn سوال | گزینه‌ها` – نظرسنجی دکمه‌ای
• `/remind 10m متن` – تنظیم یادآور (s/m/h)
• `تایمر 5m` – تایمر ساده (بدون متن)
• `/insta` – دانلود از اینستاگرام (بزودی)
• `یادداشت: متن` – ذخیرهٔ یادداشت با تاریخ
• `یادداشت‌ها` – مشاهدهٔ یادداشت‌ها
• `/clearnotes` – پاک کردن همهٔ یادداشت‌ها

👤 **پروفایل و امتیازات:**
• `امتیاز` – امتیاز و سطح شما
• `تاپ` – ۱۰ کاربر برتر
• `/referral` – کد و لینک دعوت
• `/shop` – فروشگاه آیتم‌ها
• `/buy شماره` – خرید آیتم با امتیاز
• `/items` – آیتم‌های خریداری‌شده
• `/whois @یوزرنیم` – اطلاعات کاربر

👥 **امکانات گروهی:**
• `/mute user_id دقیقه` – سکوت موقت کاربر (ادمین)
• `/warn user_id دلیل` – اخطار به کاربر (ادمین، ۳ اخطار = mute)
• `/warns user_id` – مشاهدهٔ اخطارها
• `/resetwarn user_id` – پاک کردن اخطارها
• `/diary متن` – ثبت خاطره در دفتر گروه
• `/diary` – مشاهدهٔ آخرین خاطرات گروه
• `تالار` – تالار افتخارات (سنجاق پیام)
• **ضد لینک، ضد اسپم، فیلتر کلمات نامناسب** (خودکار)

👑 **پنل سازنده (فقط مالک):**
• `/admin stats` – آمار کاربران
• `/admin broadcast متن` – پیام همگانی
• `/admin block/unblock user_id` – مسدود/آزاد کردن
• `/admin badword add/remove کلمه` – مدیریت کلمات فیلتر
• `/admin logs` – مشاهدهٔ لاگ فعالیت‌ها
• `/learn کلمه | پاسخ` – یاد دادن پاسخ به ربات
• `/unlearn کلمه` – پاک کردن کلمه از حافظه
• `/addjoke متن` / `/deljoke شماره` – مدیریت جوک‌ها
• `/bot on` / `/bot off` – خاموش/روشن کردن ربات
• `/dailyreward` – هدیهٔ ۵۰ امتیازی به کاربر برتر

💡 **نکته:** اگر ربات پیامی را بلد نباشد، سکوت می‌کند.
برای باز شدن منوی دکمه‌ای، کافی‌ست بنویسید: `منو`
"""
    await update.message.reply_text(welcome_text)

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
        if u: u["blocked"] = True; save_db(); await update.message.reply_text("کاربر مسدود شد.")
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

# ================== Mute ==================
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

# ================== Poll ==================
async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/poll سوال | گزینه۱, گزینه۲,...")
    question, opts = text.split("|",1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options)<2: return await update.message.reply_text("حداقل ۲ گزینه.")
    await update.message.reply_poll(question=question.strip(), options=options, is_anonymous=True)

# ================== Remind ==================
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
    if await check_bot_active(update, context): return
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    joke = " ".join(context.args)
    if not joke: return await update.message.reply_text("/addjoke متن جُک")
    db["jokes"].append(joke); save_db()
    await update.message.reply_text(f"✅ جُک جدید ذخیره شد. (شماره {len(db['jokes'])})")

async def deljoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args: return await update.message.reply_text("/deljoke شماره")
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(db["jokes"]):
            removed = db["jokes"].pop(idx); save_db()
            await update.message.reply_text(f"جُک حذف شد: {removed}")
        else: await update.message.reply_text("شماره نامعتبر.")
    except: await update.message.reply_text("عدد وارد کن.")

async def list_jokes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    jokes = db["jokes"]
    if not jokes: return await update.message.reply_text("هنوز هیچ جُکی نیست.")
    txt = "📋 لیست جُک‌ها:\n" + "\n".join(f"{i+1}. {j}" for i,j in enumerate(jokes))
    await update.message.reply_text(txt[:4000])

# ================== استیکر، گیف ==================
async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.sticker:
        db["stickers"].append(update.message.sticker.file_id)
        save_db()

async def animation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.animation:
        db["animations"].append(update.message.animation.file_id)
        save_db()

# ================== فروشگاه ==================
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    shop = db["shop"]
    txt = "🛍 فروشگاه (برای خرید /buy شماره):\n"
    for i, item in enumerate(shop, 1):
        txt += f"{i}. {item['name']} - 💰 {item['price']} امتیاز\n"
    await update.message.reply_text(txt)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    u = get_user(user_id)
    if not u: return await update.message.reply_text("اول /start کن.")
    if not context.args: return await update.message.reply_text("/buy شماره")
    try:
        idx = int(context.args[0]) - 1
        shop = db["shop"]
        if 0 <= idx < len(shop):
            item = shop[idx]
            if u["score"] >= item["price"]:
                u["score"] -= item["price"]
                db["user_items"].setdefault(user_id, []).append(item["name"])
                save_db()
                await update.message.reply_text(f"✅ {item['name']} خریداری شد!")
            else:
                await update.message.reply_text("❌ امتیاز کافی نداری.")
        else:
            await update.message.reply_text("شماره نامعتبر.")
    except:
        await update.message.reply_text("خطا در خرید.")

async def my_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    items = db["user_items"].get(user_id, [])
    if items:
        await update.message.reply_text("🎁 آیتم‌های شما:\n" + "\n".join(f"• {i}" for i in items))
    else:
        await update.message.reply_text("هنوز چیزی نخریدی. /shop")

# ================== Referral, Diary, Fal, Challenge ==================
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    ref_data = db["referrals"].get(user_id, {"count": 0})
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"
    await update.message.reply_text(
        f"🔗 کد دعوت شما: `{user_id}`\n"
        f"👥 تعداد دعوت‌شده: {ref_data['count']}\n"
        f"📋 لینک دعوت:\n{link}\n"
        f"با این لینک دوستانت رو دعوت کن و ۲۰ امتیاز بگیر!",
        disable_web_page_preview=True
    )

async def diary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat_id = str(update.effective_chat.id)
    args = context.args
    if args:
        entry = " ".join(args)
        db["group_diaries"].setdefault(chat_id, []).append(
            {"user": update.effective_user.first_name, "text": entry, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        )
        save_db()
        await update.message.reply_text("✅ خاطره ثبت شد.")
    else:
        entries = db["group_diaries"].get(chat_id, [])
        if entries:
            txt = "📓 خاطرات گروه:\n" + "\n".join(f"{e['time']} - {e['user']}: {e['text']}" for e in entries[-10:])
            await update.message.reply_text(txt[:4000])
        else:
            await update.message.reply_text("هنوز خاطره‌ای ثبت نشده.")

fal_list = [
    {"poem": "یوسف گم‌گشته باز آید به کنعان غم مخور / کلبهٔ احزان شود روزی گلستان غم مخور", "desc": "نوید بازگشت عزیزان"},
    {"poem": "الا یا ایها الساقی ادر کأساً و ناولها / که عشق آسان نمود اول ولی افتاد مشکل‌ها", "desc": "مسیر عشق دشوار است"},
    {"poem": "در ازل پرتو حسنت ز تجلی دم زد / عشق پیدا شد و آتش به همه عالم زد", "desc": "آغاز خلقت از عشق"},
]
async def fal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    fal = random.choice(fal_list)
    await update.message.reply_text(f"📜 فال حافظ:\n\n{fal['poem']}\n\n🔮 تفسیر: {fal['desc']}")

quotes = [
    "موفقیت یعنی رفتن از شکستی به شکست دیگر، بدون از دست دادن اشتیاق. - چرچیل",
    "تنها راه انجام کار بزرگ، عشق به کاری است که انجام می‌دهید. - استیو جابز",
    "آینده به کسانی تعلق دارد که به زیبایی رویاهایشان باور دارند. - النور روزولت",
]
daily_challenges = [
    "امروز ۳ تا تاس بنداز و مجموعش رو بگو 🎲",
    "یه جوک بگو و ببین چند لایک می‌گیری 😄",
    "با کسی که تا حالا باهاش حرف نزدی یه گفتگو کن ✨",
    "امروز ۱۰ دقیقه ورزش کن و به ربات بگو انجام دادی 💪",
    "یه عکس از غذات بگیر و بفرست 📸",
]
async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    await update.message.reply_text(f"🎯 چالش امروز:\n{random.choice(daily_challenges)}")

# ================== RPS ==================
RPS_OPTIONS = {"rock": "🪨 سنگ", "paper": "📄 کاغذ", "scissors": "✂️ قیچی"}
async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    keyboard = [
        [InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"),
         InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"),
         InlineKeyboardButton("✂️ قیچی", callback_data="rps_scissors")]
    ]
    await update.message.reply_text("انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_choice = query.data.replace("rps_", "")
    bot_choice = random.choice(list(RPS_OPTIONS.keys()))
    result = "🤝 مساوی!" if user_choice == bot_choice else (
        "🎉 بردی!" if (user_choice == "rock" and bot_choice == "scissors") or
                        (user_choice == "scissors" and bot_choice == "paper") or
                        (user_choice == "paper" and bot_choice == "rock") else "😞 باختی!")
    await query.edit_message_text(f"تو: {RPS_OPTIONS[user_choice]}\nربات: {RPS_OPTIONS[bot_choice]}\n{result}")

# ================== بازی حدس کلمه ==================
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
    await update.message.reply_text(
        f"🎮 بازی حدس کلمه شروع شد!\n{hint} ({len(word)} حرف)\nحدس خودت رو مستقیماً تایپ کن (بدون /guess).",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    chat = update.effective_chat; user = update.effective_user
    if not context.args: return await update.message.reply_text("/guess کلمه")
    guess = " ".join(context.args).strip()
    game = db["group_games"].get(str(chat.id))
    if not game or not game.get("word"): return await update.message.reply_text("بازی فعال نیست.")
    await process_guess(update.message, user, guess, game, str(chat.id))

async def end_game_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    chat_id = data[1]
    game = db["group_games"].get(chat_id)
    if not game or not game.get("word"):
        await query.edit_message_text("بازی‌ای در جریان نیست.")
        return
    word = game["word"]
    del db["group_games"][chat_id]
    save_db()
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
        if pet:
            await update.message.reply_text(f"{pet['type']} {pet['name']} | گرسنگی: {pet['hunger']}٪")
        else:
            await update.message.reply_text("پتی نداری. /pet buy <نوع> <اسم>")
    elif args[0] == "buy":
        if len(args) < 3: return await update.message.reply_text("/pet buy جوجه جوجو")
        pet_type = args[1]; pet_name = args[2]
        if pet_type not in PET_PRICES: return await update.message.reply_text("نوع نامعتبر (جوجه, سگ, گربه)")
        u = get_user(user_id)
        price = PET_PRICES[pet_type][1]
        if u["score"] < price: return await update.message.reply_text("امتیاز کافی نداری.")
        u["score"] -= price
        db["pets"][user_id] = {"name": pet_name, "type": PET_PRICES[pet_type][0], "hunger": 0, "last_fed": datetime.now().isoformat()}
        save_db()
        await update.message.reply_text(f"🎉 {PET_PRICES[pet_type][0]} {pet_name} خریداری شد!")
    elif args[0] == "feed":
        pet = db["pets"].get(user_id)
        if not pet: return await update.message.reply_text("پتی نداری.")
        pet["hunger"] = max(0, pet["hunger"] - 20)
        pet["last_fed"] = datetime.now().isoformat()
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
            add_score(user_id, 30)
            save_db()
            await update.message.reply_text("✅ مأموریت انجام شد! ۳۰ امتیاز گرفتی.")
            return
    await update.message.reply_text("شماره نامعتبر.")

# ================== قیمت ارز/طلا ==================
async def price_message(update: Update, context: ContextTypes.DEFAULT_TYPE, item: str = None):
    if not NAVASAN_API_KEY:
        await update.message.reply_text("کلید API نواسان تنظیم نشده. با سازنده تماس بگیرید.")
        return
    try:
        headers = {"Authorization": f"Bearer {NAVASAN_API_KEY}"}
        resp = http_req.get("https://api.navasan.tech/latest/", headers=headers, timeout=10)
        data = resp.json()
        if item == "دلار":
            price = data["usd"]["sell"]
            txt = f"💵 دلار: {int(price):,} تومان"
        elif item == "سکه":
            price = data["coin"]["sell"]
            txt = f"🥇 سکه: {int(price):,} تومان"
        elif item == "طلا":
            price = data["gold_18k"]["sell"]
            txt = f"💍 طلا ۱۸: {int(price):,} تومان"
        else:
            return
        await update.message.reply_text(txt)
    except:
        await update.message.reply_text("⚠️ خطا در دریافت قیمت. بعداً تلاش کنید.")

# ================== PollBtn ==================
async def pollbtn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/pollbtn سوال | گزینه۱,گزینه۲,...")
    question, opts = text.split("|",1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options) < 2: return await update.message.reply_text("حداقل ۲ گزینه.")
    poll_id = str(random.randint(10000,99999))
    db["inline_polls"][poll_id] = {"question": question, "options": options, "votes": {}}
    keyboard = [[InlineKeyboardButton(f"{opt} (0)", callback_data=f"pollbtn_{poll_id}_{i}")] for i, opt in enumerate(options)]
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
    save_db()
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

# ================== Insta (غیرفعال) ==================
async def insta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 متأسفانه در حال حاضر سرور دانلود اینستاگرام در دسترس نیست. به‌زودی جایگزین می‌شود.")

# ================== سیستم اخطار ==================
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

# ================== بازی دوز ==================
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

# ================== /whois ==================
async def whois_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    if not context.args:
        return await update.message.reply_text("/whois @یوزرنیم یا user_id")
    target = context.args[0]
    if target.startswith("@"):
        target_user = None
        for uid, u in db["users"].items():
            if u["username"] and u["username"].lower() == target[1:].lower():
                target_user = (uid, u)
                break
        if not target_user:
            return await update.message.reply_text("کاربر پیدا نشد.")
    else:
        u = get_user(target)
        if not u: return await update.message.reply_text("کاربر پیدا نشد.")
        target_user = (target, u)
    uid, u = target_user
    pet = db["pets"].get(uid, None)
    items = db["user_items"].get(uid, [])
    notes = u.get("notes", [])
    txt = f"👤 {u['first_name']} (@{u['username']})\n"
    txt += f"⭐ امتیاز: {u['score']} | سطح: {u['level']}\n"
    txt += f"🐣 پت: {pet['type']} {pet['name']}" if pet else "بدون پت"
    txt += f"\n🎁 آیتم‌ها: {', '.join(items) if items else 'ندارد'}"
    txt += f"\n📒 یادداشت‌ها: {len(notes)} عدد"
    await update.message.reply_text(txt)

# ================== پاک کردن یادداشت‌ها ==================
async def clear_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    user_id = str(update.effective_user.id)
    u = get_user(user_id)
    if u:
        u["notes"] = []
        save_db()
        await update.message.reply_text("یادداشت‌ها پاک شدند.")
    else:
        await update.message.reply_text("ثبت‌نام نکردی.")

# ================== تایمر ساده ==================
async def handle_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip()
    if not text.startswith("تایمر "):
        return False
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
    if db["guess_character"].get(str(chat.id)):
        return await update.message.reply_text("یه بازی حدس شخصیت در جریانه.")
    char = random.choice(CHARACTERS)
    db["guess_character"][str(chat.id)] = char
    save_db()
    await update.message.reply_text(f"🎭 بازی حدس شخصیت شروع شد! یک شخصیت تاریخی انتخاب کردم. برای حدس بزنید:\n`حدس میزنم [نام]`", parse_mode="Markdown")

async def handle_guess_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip()
    if not text.startswith("حدس میزنم "):
        return False
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
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except:
            pass

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_bot_active(update, context): return
    msg = update.message; chat = update.effective_chat; user = update.effective_user
    user_id = str(user.id); text = msg.text or msg.caption or ""

    if chat.id not in db["active_chats"]:
        db["active_chats"].append(chat.id)
        save_db()

    register_user(user_id, user.username or "", user.first_name or "")
    u = get_user(user_id)
    if u and u["blocked"]: return
    if is_muted(user_id):
        try: await msg.delete()
        except: pass
        return

    log_action(user_id, "message", text[:50])

    # ضد لینک
    if chat.type in ["group","supergroup"] and re.search(r'https?://', text):
        await msg.reply_text("❌ لینک ممنوع است.")
        try: await msg.delete()
        except: pass
        return

    # ضد اسپم
    if chat.type in ["group","supergroup"] and is_spam(user_id):
        try: await msg.delete(); await msg.reply_text("❌ اسپم نکنید.")
        except: pass
        return

    # فیلتر کلمات نامناسب
    if chat.type in ["group","supergroup"]:
        for bw in db["bad_words"]:
            if bw in text.lower():
                try: await msg.delete(); await msg.reply_text("⛔ پیام حذف شد.")
                except: pass
                return

    add_score(user_id)

    # حدس کلمه (بدون /guess)
    if chat.type in ["group","supergroup"] and not text.startswith("/"):
        game = db["group_games"].get(str(chat.id))
        if game and game.get("word"):
            await process_guess(msg, user, text.strip(), game, str(chat.id))
            return

    # حدس شخصیت
    if await handle_guess_character(update, context):
        return

    # تایمر
    if await handle_timer(update, context):
        return

    # پشتیبانی
    if text == "پشتیبانی":
        await msg.reply_text(f"📞 ارتباط با سازنده:\n{ADMIN_USERNAME}")
        return

    # کلمات یادگرفته‌شده
    for trigger, response in db["learned"].items():
        if trigger.lower() in text.lower():
            await msg.reply_text(response)
            return

    # جک
    if text in ["جک","جوک","جوک بگو"]:
        if db["jokes"]:
            joke = random.choice(db["jokes"])
            keyboard = [[InlineKeyboardButton("👍", callback_data="like"), InlineKeyboardButton("👎", callback_data="dislike")]]
            await msg.reply_text(joke, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await msg.reply_text("هنوز جکی یادم ندادی!")
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

    # نقل قول
    if text in ["نقل‌قول","جمله"]:
        await msg.reply_text(random.choice(quotes))
        return

    # ساعت / تاریخ
    if text == "ساعت":
        await msg.reply_text(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        return
    if text in ["تاریخ","امروز"]:
        now = jdatetime.datetime.now()
        await msg.reply_text(f"📅 {now.strftime('%Y/%m/%d')} - {now.strftime('%A')}")
        return

    # قیمت‌ها
    if text in ["دلار","سکه","طلا"]:
        await price_message(update, context, text)
        return

    # تالار افتخارات
    if text == "تالار":
        top = get_top_users(5)
        if top:
            txt = "🏆 تالار افتخارات:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i,r in enumerate(top))
            sent = await msg.reply_text(txt)
            try: await sent.pin(disable_notification=True)
            except: pass
        return

    # امتیاز/تاپ
    if text == "امتیاز":
        await msg.reply_text(f"🌟 {u['score']} | سطح {u['level']}")
        return
    if text == "تاپ":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i,r in enumerate(top)) if top else "خالی."
        await msg.reply_text(txt)
        return

    # یادداشت (با تاریخ)
    if text.startswith("یادداشت:"):
        note = text.replace("یادداشت:","",1).strip()
        if note:
            u["notes"].append({"text": note, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
            save_db()
            await msg.reply_text("✅ ذخیره شد.")
        return
    if text == "یادداشت‌ها":
        notes = u.get("notes",[])
        if notes:
            txt = "📒 یادداشت‌ها:\n" + "\n".join(f"• {n['time']}: {n['text']}" for n in notes[-10:])
            await msg.reply_text(txt)
        else:
            await msg.reply_text("یادداشتی نداری.")
        return

    # منو
    if text == "منو":
        await msg.reply_text("📋 منوی اصلی:", reply_markup=get_main_menu_keyboard())
        return

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

    if msg.photo:
        await msg.reply_text("📸 عکس دریافت شد.")
        return

    # ناشناخته: سکوت

# ================== دکمه‌ها ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data
    user_id = str(query.from_user.id)

    if data.startswith("ttt_"):
        await tic_tac_toe_button(update, context)
        return
    if data == "menu_main": await query.edit_message_text("منوی اصلی:", reply_markup=get_main_menu_keyboard())
    elif data == "menu_games": await query.edit_message_text("بازی‌ها:", reply_markup=get_games_keyboard())
    elif data == "menu_tools": await query.edit_message_text("ابزارها:", reply_markup=get_tools_keyboard())
    elif data == "menu_profile": await query.edit_message_text("پروفایل:", reply_markup=get_profile_keyboard())
    elif data == "rps_menu": await query.message.reply_text("/rps")
    elif data == "menu_pollbtn": await query.message.reply_text("/pollbtn")
    elif data == "menu_remind": await query.message.reply_text("/remind")
    elif data == "menu_shop": await query.message.reply_text("/shop")
    elif data in ("price_dollar","price_coin","price_gold"):
        item = {"price_dollar":"دلار","price_coin":"سکه","price_gold":"طلا"}[data]
        await price_message(update, context, item)
    elif data in ("like","dislike"):
        await query.answer(f"شما {'👍' if data=='like' else '👎'} دادید")
    elif data.startswith("rps_"):
        await handle_rps(update, context)
    elif data == "dice": await query.message.reply_dice(emoji="🎲")
    elif data == "dart": await query.message.reply_dice(emoji="🎯")
    elif data == "creator": await query.message.reply_text("یاسین چنگیزی ساخته منو ❤️")
    elif data == "score":
        u = get_user(user_id)
        await query.message.reply_text(f"🌟 امتیاز: {u['score']}" if u else "نیستی.")
    elif data == "top":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i,r in enumerate(top)) if top else "خالی."
        await query.message.reply_text(txt)
    elif data == "shownotes":
        u = get_user(user_id)
        notes = u.get("notes",[]) if u else []
        if notes:
            txt = "📒 یادداشت‌ها:\n" + "\n".join(f"• {n['time']}: {n['text']}" for n in notes[-10:])
            await query.message.reply_text(txt)
        else:
            await query.message.reply_text("یادداشتی نداری.")
    elif data == "help": await query.message.reply_text("/start")

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name} 🌹")

# ================== اجرا ==================
def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    # سلام خودکار هر ۶ ساعت
    app.job_queue.run_repeating(auto_greet, interval=21600, first=10)

    # همه هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("bot", bot_toggle))
    app.add_handler(CommandHandler("dailyreward", daily_reward))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("warns", warns_list))
    app.add_handler(CommandHandler("resetwarn", reset_warns))
    app.add_handler(CommandHandler("duel", duel_command))
    app.add_handler(CommandHandler("whois", whois_command))
    app.add_handler(CommandHandler("clearnotes", clear_notes))
    app.add_handler(CommandHandler("guesswho", guesswho_command))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("poll", poll_command))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("learn", learn_command))
    app.add_handler(CommandHandler("unlearn", unlearn_command))
    app.add_handler(CommandHandler("addjoke", addjoke_command))
    app.add_handler(CommandHandler("deljoke", deljoke_command))
    app.add_handler(CommandHandler("jokes", list_jokes_command))
    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("items", my_items_command))
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
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    app.add_handler(MessageHandler(filters.ANIMATION, animation_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(pollbtn_vote, pattern="^pollbtn_"))
    app.add_handler(CallbackQueryHandler(end_game_button, pattern="^endgame_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات نهایی کامل اجرا شد.")
    app.run_polling()

if __name__ == "__main__":
    main()

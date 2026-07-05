import os, json, random, re, asyncio, threading
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8391932958          # ⚠️ آیدی عددی خودت
ADMIN_USERNAME = "@YasinChangizi"   # ⚠️ یوزرنیم تلگرامت

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
db.setdefault("stickers", [])          # جدید: لیست ID استیکرها
db.setdefault("shop", [                # جدید: فروشگاه
    {"name": "🏅 مدال طلا", "price": 100},
    {"name": "🥈 مدال نقره", "price": 50},
    {"name": "💎 نشان الماس", "price": 200}
])
db.setdefault("user_items", {})        # جدید: آیتم‌های خریداری‌شده هر کاربر

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

def register_user(user_id: str, username: str, first_name: str):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": username, "first_name": first_name,
            "score": 0, "level": 1, "blocked": False,
            "notes": [], "muted_until": None
        }
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

# ================== دستورات عمومی ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(str(user.id), user.username or "", user.first_name or "")
    welcome_text = """
🤖 به Diminol-bot خوش اومدی! 
من ربات همه‌فن‌حریف تو هستم، ساخته‌ی یاسین چنگیزی ❤️

✨ اینجام تا چت رو برات جذاب‌تر کنم، باهات بازی کنم، بهت یاد بدم، و توی گروه کمکت کنم.

📌 کارهایی که می‌تونم انجام بدم:

🎯 سرگرمی و بازی:
▫️ تاس یا دارت → یه تاس یا دارت میندازم 🎲
▫️ جک / جوک / جوک بگو → یه جوک بامزه برات میگم 😄
▫️ استیکر → یه استیکر تصادفی از بین اونایی که برام فرستادین برمی‌گردونم
▫️ قرعه‌کشی (فقط توی گروه) → یه نفر رو به قید قرعه انتخاب میکنم 🎉

🧠 یادگیری و پرسش و پاسخ:
▫️ سازنده میتونه با /learn به من حرف یاد بده.
▫️ اگه حرفی بلد باشم، هرجا توی پیامت بیاد جوابش رو میدم.

👤 اطلاعات کاربر:
▫️ امتیاز → امتیاز و سطحت رو ببین
▫️ تاپ → جدول بهترین کاربرا رو نشون بده
▫️ یادداشت: متن → یه یادداشت شخصی برات ذخیره کنم
▫️ یادداشت‌ها → نوشته‌هات رو نشون بدم
▫️ پشتیبانی → راه ارتباط با سازنده رو بهت میدم

🛍 فروشگاه:
▫️ /shop → آیتم‌های قابل خرید با امتیاز رو ببین
▫️ /buy شماره → یه آیتم از فروشگاه بخری
▫️ /items → آیتم‌هایی که خریدی رو ببینی

🛠 ابزارهای کاربردی:
▫️ /poll سوال | گزینه۱, گزینه۲ → یه نظرسنجی بسازم 📊
▫️ /remind 10m پیام → بعد از مدت معین یادآوری کنم ⏰
▫️ نقل‌قول → یه جمله‌ی معروف برات میگم

👥 امکانات گروهی:
▫️ لینک ممنوع → لینک‌ها رو پاک میکنم و هشدار میدم
▫️ ضد اسپم → پیام‌های انبوه رو تشخیص میدم
▫️ کلمات نامناسب → با مدیریت سازنده پاک میشن
▫️ /mute آیدی مدت → کاربر رو برای دقایقی بی‌صدا میکنم (مخصوص ادمین‌ها)
▫️ خوش‌آمدگویی → اعضای جدید رو تحویل میگیرم 🌹

👑 پنل سازنده (فقط با /admin):
▫️ مدیریت کاربران، آمار، پیام همگانی، فیلتر کلمات، دیدن لاگ و...

💬 نکته: اگه چیزی بلد نباشم، سکوت میکنم. فقط وقتی حرفی رو بلد باشم جواب میدم.

🚀 برای شروع دوباره، /start رو بزن.
    """
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("برای دیدن راهنمای کامل، /start رو بزن.")

# ================== پنل ادمین (همان قبلی) ==================
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

# ================== Mute / Poll / Remind (بدون تغییر) ==================
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if "|" not in text: return await update.message.reply_text("/poll سوال | گزینه۱, گزینه۲,...")
    question, opts = text.split("|",1)
    options = [o.strip() for o in opts.split(",") if o.strip()]
    if len(options)<2: return await update.message.reply_text("حداقل ۲ گزینه.")
    await update.message.reply_poll(question=question.strip(), options=options, is_anonymous=True)

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    if not context.args: return await update.message.reply_text("/unlearn کلمه")
    trigger = context.args[0]
    if trigger in db["learned"]:
        del db["learned"][trigger]; save_db()
        await update.message.reply_text(f"«{trigger}» از حافظه پاک شد.")
    else:
        await update.message.reply_text("این کلمه تو حافظه نیست.")

async def addjoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("❌ فقط سازنده.")
    joke = " ".join(context.args)
    if not joke: return await update.message.reply_text("/addjoke متن جُک")
    db["jokes"].append(joke); save_db()
    await update.message.reply_text(f"✅ جُک جدید ذخیره شد. (شماره {len(db['jokes'])})")

async def deljoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    jokes = db["jokes"]
    if not jokes: return await update.message.reply_text("هنوز هیچ جُکی نیست.")
    txt = "📋 لیست جُک‌ها:\n" + "\n".join(f"{i+1}. {j}" for i,j in enumerate(jokes))
    await update.message.reply_text(txt[:4000])

# ================== استیکر ==================
async def sticker_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    if sticker:
        db["stickers"].append(sticker.file_id)
        save_db()
        # بی‌صدا ذخیره کن

# ================== فروشگاه ==================
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    shop = db["shop"]
    if not shop: return await update.message.reply_text("فروشگاه فعلاً خالیه.")
    txt = "🛍 فروشگاه (برای خرید /buy شماره):\n"
    for i, item in enumerate(shop, 1):
        txt += f"{i}. {item['name']} - 💰 {item['price']} امتیاز\n"
    await update.message.reply_text(txt)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_id = str(update.effective_user.id)
    items = db["user_items"].get(user_id, [])
    if items:
        await update.message.reply_text("🎁 آیتم‌های شما:\n" + "\n".join(f"• {i}" for i in items))
    else:
        await update.message.reply_text("هنوز چیزی نخریدی. با /shop ببین.")

# ================== نقل قول ==================
quotes = [
    "موفقیت یعنی رفتن از شکستی به شکست دیگر، بدون از دست دادن اشتیاق. - چرچیل",
    "تنها راه انجام کار بزرگ، عشق به کاری است که انجام می‌دهید. - استیو جابز",
    "آینده به کسانی تعلق دارد که به زیبایی رویاهایشان باور دارند. - النور روزولت",
    "اگر می‌خواهی چیزی را که هرگز نداشته‌ای به دست بیاوری، باید کاری کنی که هرگز انجام نداده‌ای.",
    "شما می‌توانید هر چیزی را که ذهنتان باور داشته باشد، به دست آورید."
]

# ================== تالار افتخارات (سنجاق) ==================
async def hall_of_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ["group","supergroup"]:
        return await update.message.reply_text("فقط توی گروه.")
    top = get_top_users(5)
    if not top: return await update.message.reply_text("کسی نیست.")
    txt = "🏆 تالار افتخارات:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} - {r[1]['score']} امتیاز" for i, r in enumerate(top))
    sent = await update.message.reply_text(txt)
    try:
        await sent.pin(disable_notification=True)
    except:
        await update.message.reply_text("برای سنجاق کردن ادمینم کن.")

# ================== مدیریت پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    user_id = str(user.id)
    text = msg.text or msg.caption or ""

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
        try:
            await msg.delete()
            await msg.reply_text("❌ اسپم نکنید.")
        except: pass
        return

    # فیلتر کلمات نامناسب
    if chat.type in ["group","supergroup"]:
        for bw in db["bad_words"]:
            if bw in text.lower():
                try:
                    await msg.delete()
                    await msg.reply_text("⛔ پیام حذف شد (کلمه نامناسب).")
                except: pass
                return

    add_score(user_id)

    # پشتیبانی
    if text == "پشتیبانی":
        await msg.reply_text(f"📞 ارتباط با سازنده:\n{ADMIN_USERNAME}")
        return

    # کلمات یادگرفته‌شده
    for trigger, response in db["learned"].items():
        if trigger.lower() in text.lower():
            await msg.reply_text(response)
            return

    # جُک
    if text in ["جک", "جوک", "جوک بگو"]:
        if db["jokes"]:
            joke = random.choice(db["jokes"])
            keyboard = [[InlineKeyboardButton("👍", callback_data=f"like"), InlineKeyboardButton("👎", callback_data=f"dislike")]]
            await msg.reply_text(joke, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await msg.reply_text("هنوز هیچ جُکی یادم ندادی! 🥲")
        return

    # استیکر
    if text == "استیکر":
        if db["stickers"]:
            await msg.reply_sticker(sticker=random.choice(db["stickers"]))
        else:
            await msg.reply_text("هنوز هیچ استیکری برام نفرستادی.")
        return

    # نقل‌قول
    if text in ["نقل‌قول", "جمله"]:
        await msg.reply_text(random.choice(quotes))
        return

    # تالار افتخارات
    if text == "تالار":
        await hall_of_fame(update, context)
        return

    # امتیاز
    if text == "امتیاز":
        await msg.reply_text(f"🌟 امتیاز: {u['score']} | سطح: {u['level']}")
        return

    # تاپ
    if text == "تاپ":
        top = get_top_users(10)
        txt = "🏆 برترین‌ها:\n" + "\n".join(f"{i+1}. {r[1]['first_name']} ({r[1]['score']})" for i, r in enumerate(top)) if top else "خالی."
        await msg.reply_text(txt)
        return

    # یادداشت
    if text.startswith("یادداشت:"):
        note = text.replace("یادداشت:", "", 1).strip()
        if note:
            u["notes"].append(note); save_db()
            await msg.reply_text("✅ ذخیره شد.")
        return

    if text == "یادداشت‌ها":
        notes = u.get("notes", [])
        await msg.reply_text("📒 یادداشت‌ها:\n" + "\n".join(f"• {n}" for n in notes) if notes else "یادداشتی نداری.")
        return

    # منو
    if text == "منو":
        keyboard = [
            [InlineKeyboardButton("🎲 تاس", callback_data="dice"), InlineKeyboardButton("🎯 دارت", callback_data="dart")],
            [InlineKeyboardButton("⭐ امتیاز", callback_data="score"), InlineKeyboardButton("🏆 تاپ", callback_data="top")],
            [InlineKeyboardButton("👤 سازنده", callback_data="creator"), InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
        ]
        await msg.reply_text("منو:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # تاس / دارت
    if text == "تاس":
        await msg.reply_dice(emoji="🎲")
        return
    if text == "دارت":
        await msg.reply_dice(emoji="🎯")
        return

    # قرعه‌کشی
    if text == "قرعه‌کشی" and chat.type in ["group","supergroup"]:
        try:
            members = [m.user.id async for m in context.bot.get_chat_members(chat.id) if not m.user.is_bot]
            winner = random.choice(members)
            await msg.reply_text(f"🎉 برنده: <a href='tg://user?id={winner}'>{winner}</a>", parse_mode="HTML")
        except: pass
        return

    # عکس
    if msg.photo:
        await msg.reply_text("📸 عکس دریافت شد.")
        return

    # --- پیام‌های ناشناخته: سکوت ---

# ================== دکمه‌ها ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(query.from_user.id)
    if data in ("like", "dislike"):
        # می‌تونیم اینجا آمار لایک جمع کنیم، فعلاً فقط یه واکنش
        reaction = "👍" if data == "like" else "👎"
        await query.answer(f"شما {reaction} دادید")
        return

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
        await query.message.reply_text("/start\n/admin\n/learn\n/jokes\n/shop\n/items\nنقل‌قول\nاستیکر\nتالار")

# ================== خوش‌آمدگویی ==================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(f"خوش آمدی {member.first_name} 🌹")

# ================== اجرا ==================
def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
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
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    print("✅ ربات با فروشگاه، نقل‌قول، استیکر، تالار افتخارات اجرا شد.")
    app.run_polling()

if __name__ == "__main__":
    main()

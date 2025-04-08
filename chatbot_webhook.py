import os
import json
import logging
import configparser
import firebase_admin
from firebase_admin import credentials, firestore

from flask import Flask, request
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from ChatGPT_HKBU import HKBU_ChatGPT

# 初始化 Flask 应用
app = Flask(__name__)
telegram_app = None  # 全局 Telegram 应用
chatgpt = None
db = None

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# 配置读取函数
def get_config(section: str, key: str, fallback: str = None) -> str:
    env_name = f"{section}_{key}".upper()
    value = os.getenv(env_name) or os.getenv(key.upper())
    if value:
        return value

    if not hasattr(get_config, "config"):
        get_config.config = configparser.ConfigParser()
        get_config.config.read("config.ini")

    try:
        return get_config.config.get(section, key, fallback=fallback)
    except (configparser.NoSectionError, configparser.NoOptionError):
        if fallback is not None:
            return fallback
        raise ValueError(f"Missing config: {section}.{key}")


# === 命令处理器 ===
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyword = context.args[0]
        doc_ref = db.collection("keyword_counts").document(keyword)
        doc_ref.set({"count": firestore.Increment(1)}, merge=True)
        count = doc_ref.get().to_dict().get("count", 1)
        await update.message.reply_text(f'You have said "{keyword}" for {count} times.')
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <keyword>")
    except Exception as e:
        logger.error(f"Error in /add: {str(e)}")
        await update.message.reply_text("An error occurred.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/add <keyword> - Count keyword usage\n"
        "/help - Show help\n"
        "/hello <name> - Greet a user"
    )

async def hello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await update.message.reply_text(f"Good day, {context.args[0]}!")
    else:
        await update.message.reply_text("Usage: /hello <name>")

async def equiped_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text
        reply_message = chatgpt.submit(user_message)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)
    except Exception as e:
        logger.error(f"ChatGPT Error: {str(e)}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Error responding.")


# === Webhook 端点 ===
@app.route("/")
def health_check():
    return "🤖 Bot is running on Webhook!", 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "ok", 200


# === 主函数：初始化服务 ===
def main():
    global telegram_app, chatgpt, db

    # 初始化 Firebase
    firebase_config = os.getenv("FIREBASE_CONFIG")
    if firebase_config:
        cred = credentials.Certificate(json.loads(firebase_config))
    else:
        firebase_key_path = get_config("DEFAULT", "FIREBASE_KEY_PATH", "firebase_key.json")
        cred = credentials.Certificate(firebase_key_path)

    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firestore initialized.")

    # 初始化 ChatGPT
    chatgpt = HKBU_ChatGPT(
        base_url=get_config("CHATGPT", "BASTCURL"),
        model=get_config("CHATGPT", "MODELNAME"),
        api_version=get_config("CHATGPT", "APIVERSION"),
        access_token=get_config("CHATGPT", "ACCESS_TOKEN"),
    )

    # 初始化 Telegram Bot
    token = get_config("TELEGRAM", "ACCESS_TOKEN")
    telegram_app = ApplicationBuilder().token(token).build()

    # 添加处理器
    telegram_app.add_handler(CommandHandler("add", add))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("hello", hello_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), equiped_chatgpt))

    # 设置 Webhook
    webhook_url = os.getenv("WEBHOOK_URL")  # 例如: https://your-service-name.a.run.app/webhook
    if webhook_url:
        asyncio.run(telegram_app.bot.set_webhook(webhook_url))
        logger.info(f"🌐 Webhook set to: {webhook_url}")
    else:
        logger.warning("⚠️ WEBHOOK_URL not set!")


# === 运行程序 ===
if __name__ == "__main__":
    main()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
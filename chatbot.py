import os
import logging
import json
import configparser
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from ChatGPT_HKBU import HKBU_ChatGPT

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# 全局变量
global db
global chatgpt

# 获取配置函数：优先使用环境变量，其次读取 config.ini
def get_config(section: str, key: str, fallback: str = None) -> str:
    value = os.getenv(key)
    if value:
        return value
    if not hasattr(get_config, "config"):
        config = configparser.ConfigParser()
        config.read("config.ini")
        get_config.config = config
    result = get_config.config.get(section, key, fallback=fallback)
    if result is None:
        raise ValueError(f"Configuration for {key} is missing!")
    return result

# /add 命令
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
        logger.error(f"Error in add command: {str(e)}")
        await update.message.reply_text("Sorry, something went wrong. Please try again later.")

# /help 命令
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/add <keyword> - Count the frequency of a keyword\n"
        "/help - Show this help message\n"
        "/hello <name> - Greet a user"
    )

# /hello 命令
async def hello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        name = context.args[0]
        await update.message.reply_text(f"Good day, {name}!")
    else:
        await update.message.reply_text("Usage: /hello <name>")

# ChatGPT 响应消息
async def equiped_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text
        reply_message = chatgpt.submit(user_message)
        logger.info(f"User: {user_message}, ChatGPT: {reply_message}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)
    except Exception as e:
        logger.error(f"Error in ChatGPT response: {str(e)}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I'm having trouble responding right now.")

# 主入口
def main():

    # 调试输出环境变量
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if telegram_token:
        logger.info(f"Telegram Token loaded successfully: {telegram_token[:5]}...")  # 显示部分token，避免暴露完整token
    else:
        logger.error("❌ TELEGRAM_TOKEN is not set!")
        raise ValueError("TELEGRAM_TOKEN is missing!")

    # 初始化 Firestore
    try:
        firebase_config = os.getenv("FIREBASE_CONFIG")
        if firebase_config:
            firebase_config_dict = json.loads(firebase_config)
            cred = credentials.Certificate(firebase_config_dict)
        else:
            firebase_key_path = get_config("DEFAULT", "FIREBASE_KEY_PATH", "firebase_key.json")
            cred = credentials.Certificate(firebase_key_path)

        firebase_admin.initialize_app(cred)
        global db
        db = firestore.client()
        logger.info("✅ Connected to Firestore successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Firestore: {str(e)}")
        raise

    # Telegram Token
    telegram_token = get_config("TELEGRAM", "ACCESS_TOKEN")
    if not telegram_token:
        logger.error("❌ TELEGRAM_TOKEN is not set!")
        raise ValueError("TELEGRAM_TOKEN is missing!")

    # 初始化 ChatGPT 客户端
    global chatgpt
    chatgpt = HKBU_ChatGPT(
        base_url=get_config("CHATGPT", "BASTCURL"),
        model=get_config("CHATGPT", "MODELNAME"),
        api_version=get_config("CHATGPT", "APIVERSION"),
        access_token=get_config("CHATGPT", "ACCESS_TOKEN"),
    )

    # 创建 Telegram 应用
    application = ApplicationBuilder().token(telegram_token).build()

    # 注册处理器
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("hello", hello_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), equiped_chatgpt))

    logger.info("🤖 Bot started! Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()

import os
import json
import logging
import configparser
import firebase_admin
from firebase_admin import credentials, firestore
from quart import Quart, request
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from pythonjsonlogger import jsonlogger
from ChatGPT_HKBU import HKBU_ChatGPT
import requests

app = Quart(__name__)
telegram_app = None
chatgpt = None
db = None

def setup_logging():
    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s %(user_id)s %(type)s',
        rename_fields={'levelname': 'severity', 'asctime': 'timestamp'},
        datefmt='%Y-%m-%dT%H:%M:%SZ'
    )
    log_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.setLevel(logging.INFO)
    
    # Reduce noise from libraries
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

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

def get_maimai_player_profile(player_id: str) -> dict:
    token = os.getenv("MAIMAI_PERSONAL_TOKEN")  # 从环境变量获取 API 密钥
    url = f"https://maimai.lxns.net/api/v0/user/maimai/player"
    
    headers = {
        "X-User-Token": token  # 在请求头中加入个人 API 密钥
    }
    
    params = {"player_id": player_id}  # 使用 player_id 查询玩家信息
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()  # 如果响应失败，会抛出异常
        return response.json()  # 返回 JSON 格式的玩家资料
    except requests.RequestException as e:
        logger.error("Maimai API failed", extra={
            "player_id": player_id,
            "error": str(e),
            "type": "maimai_api_error"
        })
        return {"error": "无法获取玩家资料"}


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyword = context.args[0]
        doc_ref = db.collection("keyword_counts").document(keyword)
        doc_ref.set({"count": firestore.Increment(1)}, merge=True)
        count = doc_ref.get().to_dict().get("count", 1)
        
        logger.info("Keyword counted", extra={
            "user_id": update.effective_user.id,
            "keyword": keyword,
            "count": count,
            "type": "keyword_count"
        })
        
        await update.message.reply_text(f'You have said "{keyword}" for {count} times.')
    except (IndexError, ValueError):
        logger.warning("Invalid /add command", extra={
            "user_id": update.effective_user.id,
            "args": context.args,
            "type": "command_error"
        })
        await update.message.reply_text("Usage: /add <keyword>")
    except Exception as e:
        logger.error("/add command failed", extra={
            "user_id": update.effective_user.id,
            "error": str(e),
            "type": "command_error"
        })
        await update.message.reply_text("An error occurred.")

async def maimai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if not context.args:
            logger.warning("Missing player ID", extra={
                "user_id": user_id,
                "type": "maimai_command"
            })
            await update.message.reply_text("请提供玩家 ID，例如：/maimai 玩家123")
            return

        player_id = context.args[0]
        logger.info("Fetching maimai profile", extra={
            "user_id": user_id,
            "player_id": player_id,
            "type": "maimai_command"
        })

        profile = get_maimai_player_profile(player_id)
        if "error" in profile:
            logger.warning("Maimai profile error", extra={
                "user_id": user_id,
                "player_id": player_id,
                "error": profile["error"],
                "type": "maimai_command"
            })
            await update.message.reply_text(profile["error"])
        else:
            profile_text = f"玩家 ID: {profile['player_id']}\n昵称: {profile['nickname']}\n等级: {profile['level']}"
            logger.info("Maimai profile fetched", extra={
                "user_id": user_id,
                "player_id": player_id,
                "type": "maimai_command"
            })
            await update.message.reply_text(profile_text)
    except Exception as e:
        logger.error("Maimai command failed", extra={
            "user_id": user_id,
            "error": str(e),
            "type": "command_error"
        })
        await update.message.reply_text("查询时发生错误")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Help command", extra={
        "user_id": update.effective_user.id,
        "type": "help_command"
    })
    await update.message.reply_text(
        "Available commands:\n"
        "/add <keyword> - Count keyword usage\n"
        "/help - Show help\n"
        "/hello <name> - Greet a user\n"
        "/maimai <player_id> - 查询舞萌 DX 玩家资料"
    )

async def hello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if context.args:
            name = context.args[0]
            logger.info("Hello command", extra={
                "user_id": user_id,
                "name": name,
                "type": "hello_command"
            })
            await update.message.reply_text(f"Good day, {name}!")
        else:
            logger.warning("Missing name for hello", extra={
                "user_id": user_id,
                "type": "command_error"
            })
            await update.message.reply_text("Usage: /hello <name>")
    except Exception as e:
        logger.error("Hello command failed", extra={
            "user_id": user_id,
            "error": str(e),
            "type": "command_error"
        })
        await update.message.reply_text("An error occurred.")

async def equiped_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        user_message = update.message.text
        logger.info("Processing user message", extra={
            "user_id": user_id,
            "message": user_message[:100],  # Log first 100 chars to avoid sensitive data
            "type": "chat_message"
        })

        reply = chatgpt.submit(user_message, user_id=user_id)

        if isinstance(reply, dict):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=reply["text"]
            )
            if "image_url" in reply:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=reply["image_url"]
                )
                logger.debug("Image sent", extra={
                    "user_id": user_id,
                    "type": "chat_image"
                })
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=str(reply)
            )
    except Exception as e:
        logger.error("Chat processing failed", extra={
            "user_id": user_id,
            "error": str(e),
            "type": "chat_error"
        })
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Error responding."
        )

@app.route("/")
async def health_check():
    logger.info("Health check", extra={"type": "health_check"})
    return "🤖 Bot is running on Webhook!", 200

@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    try:
        update = Update.de_json(await request.get_json(), telegram_app.bot)
        
        if not telegram_app._initialized:
            await telegram_app.initialize()
        
        await telegram_app.process_update(update)
        
        logger.info("Webhook processed", extra={
            "update_id": update.update_id,
            "type": "webhook"
        })
        return "ok", 200
    except Exception as e:
        logger.error("Webhook failed", extra={
            "error": str(e),
            "type": "webhook_error"
        })
        return "error", 500

@app.after_request
async def log_request(response):
    try:
        data = await request.get_json() if request.method == "POST" else {}
        user_id = str(data.get("message", {}).get("from", {}).get("id", "anonymous"))
        
        logger.info("Request processed", extra={
            "user_id": user_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "type": "request"
        })
    except Exception as e:
        logger.error("Request logging failed", extra={
            "error": str(e),
            "type": "logging_error"
        })
    return response

def main():
    global telegram_app, chatgpt, db
    
    setup_logging()
    logger.info("Initializing application", extra={"type": "startup"})

    try:
        firebase_config = os.getenv("FIREBASE_CONFIG")
        if firebase_config:
            cred = credentials.Certificate(json.loads(firebase_config))
        else:
            firebase_key_path = get_config("DEFAULT", "FIREBASE_KEY_PATH", "firebase_key.json")
            cred = credentials.Certificate(firebase_key_path)

        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("Firestore initialized", extra={"type": "startup"})
    except Exception as e:
        logger.critical("Firebase init failed", extra={
            "error": str(e),
            "type": "startup_error"
        })
        raise

    try:
        chatgpt = HKBU_ChatGPT(
            base_url=get_config("CHATGPT", "BASTCURL"),
            model=get_config("CHATGPT", "MODELNAME"),
            api_version=get_config("CHATGPT", "APIVERSION"),
            access_token=get_config("CHATGPT", "ACCESS_TOKEN"),
            firestore_db=db,
        )
        logger.info("ChatGPT initialized", extra={"type": "startup"})
    except Exception as e:
        logger.critical("ChatGPT init failed", extra={
            "error": str(e),
            "type": "startup_error"
        })
        raise

    try:
        token = get_config("TELEGRAM", "ACCESS_TOKEN")
        telegram_app = ApplicationBuilder().token(token).build()

        telegram_app.add_handler(CommandHandler("add", add))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("hello", hello_command))
        telegram_app.add_handler(CommandHandler("maimai", maimai_command))
        telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), equiped_chatgpt))

        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            asyncio.run(telegram_app.bot.set_webhook(webhook_url))
            logger.info("Webhook configured", extra={
                "webhook_url": webhook_url,
                "type": "startup"
            })
        else:
            logger.warning("WEBHOOK_URL not set", extra={"type": "startup"})
    except Exception as e:
        logger.critical("Telegram init failed", extra={
            "error": str(e),
            "type": "startup_error"
        })
        raise

if __name__ == "__main__":
    main()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
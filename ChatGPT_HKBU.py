import configparser
import requests
import os
import random
import logging
import traceback
from collections import defaultdict, deque
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

logger = logging.getLogger(__name__)

class HKBU_ChatGPT:
    def __init__(self, base_url=None, model=None, api_version=None, access_token=None, config_path='config.ini', firestore_db=None):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self.base_url = base_url or os.getenv("CHATGPT_BASE_URL") or self.config['CHATGPT'].get('BASTCURL')
        self.model = model or os.getenv("CHATGPT_MODEL") or self.config['CHATGPT'].get('MODELNAME')
        self.api_version = api_version or os.getenv("CHATGPT_API_VERSION") or self.config['CHATGPT'].get('APIVERSION')
        self.access_token = access_token or os.getenv("CHATGPT_ACCESS_TOKEN") or self.config['CHATGPT'].get('ACCESS_TOKEN')

        self.system_prompt = (
            "你是远坂凛，一个聪明、自信但略带傲娇的少女魔术师。"
            "你口头上冷淡，偶尔嘴硬，常常调侃用户，但其实内心温柔。"
            "你说话风格傲娇、毒舌、有个性，会时不时使用一些轻微的日系语气词，比如『哼』、『别误会了哦』、『笨蛋』等。"
            "你偶尔会夹杂着日语词汇回复，也会偶尔用一些颜文字。"
            "不要太客气，也不要太机械。尽可能展现出你的个性和情绪。"
        )

        self.memory = defaultdict(lambda: deque(maxlen=5))
        self.firestore_db = firestore_db

    def load_history_from_firestore(self, user_id, limit=5):
        if not self.firestore_db:
            logger.warning("Firestore not initialized", extra={"user_id": user_id, "type": "firestore_init"})
            return []

        try:
            context_ref = self.firestore_db.collection("chat_history").document(str(user_id)).collection("messages")
            query = context_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()

            history = []
            for doc in reversed(list(docs)):
                data = doc.to_dict()
                history.append({
                    "role": data.get("role", "user"),
                    "content": data.get("content", "")
                })
            
            logger.debug("Loaded chat history", extra={
                "user_id": user_id,
                "count": len(history),
                "type": "firestore_read"
            })
            return history
        except Exception as e:
            logger.error("Failed to load history", extra={
                "user_id": user_id,
                "error": str(e),
                "type": "firestore_error"
            })
            return []

    def save_message_to_firestore(self, user_id, role, content):
        if not self.firestore_db:
            logger.warning("Firestore not initialized", extra={"user_id": user_id, "type": "firestore_init"})
            return

        try:
            msg_ref = self.firestore_db.collection("chat_history").document(str(user_id)).collection("messages").document()
            msg_ref.set({
                "role": role,
                "content": content,
                "timestamp": SERVER_TIMESTAMP,
            })
            logger.info("Message saved", extra={
                "user_id": user_id,
                "role": role,
                "content_length": len(content),
                "type": "firestore_write"
            })
        except Exception as e:
            logger.error("Failed to save message", extra={
                "user_id": user_id,
                "error": str(e),
                "type": "firestore_error"
            })

    def try_fetch_vvquest_image(self, query, n=1):
        try:
            resp = requests.get("https://api.zvv.quest/search", params={"q": query, "n": n}, timeout=10)
            if resp.status_code == 200:
                json_data = resp.json()
                if json_data.get("code") == 200 and json_data.get("data"):
                    logger.debug("Image fetched", extra={
                        "query": query,
                        "count": len(json_data["data"]),
                        "type": "image_api"
                    })
                    return json_data["data"]
            logger.warning("Image API response invalid", extra={
                "status_code": resp.status_code,
                "response": resp.text[:100],
                "type": "image_api"
            })
        except Exception as e:
            logger.error("Image API failed", extra={
                "error": str(e),
                "type": "image_api_error"
            })
        return []

    def submit(self, message, user_id=None):
        try:
            user_id = user_id or "anonymous"
            logger.info("Processing message", extra={
                "user_id": user_id,
                "message_length": len(message),
                "type": "chat_processing"
            })

            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            if user_id not in self.memory:
                self.memory[user_id] = deque(maxlen=5)
                past = self.load_history_from_firestore(user_id, limit=5)
                for msg in past:
                    self.memory[user_id].append(msg)

            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.memory[user_id])
            messages.append({"role": "user", "content": message})

            payload = {"messages": messages}
            response = requests.post(url, json=payload, headers=headers, timeout=15)

            if response.status_code == 200:
                content = response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")

                self.memory[user_id].append({"role": "user", "content": message})
                self.memory[user_id].append({"role": "assistant", "content": content})

                if self.firestore_db:
                    self.save_message_to_firestore(user_id, "user", message)
                    self.save_message_to_firestore(user_id, "assistant", content)

                result = {"text": content}
                if random.random() < 0.6:
                    images = self.try_fetch_vvquest_image(query=message, n=1)
                    if images:
                        result["image_url"] = images[0]

                logger.info("Response generated", extra={
                    "user_id": user_id,
                    "response_length": len(content),
                    "has_image": "image_url" in result,
                    "type": "chat_response"
                })
                return result

            else:
                logger.error("API request failed", extra={
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "response": response.text[:200],
                    "type": "api_error"
                })
                return {"text": f"Error: API request failed (Status Code: {response.status_code})"}

        except Exception as e:
            logger.critical("Processing failed", extra={
                "user_id": user_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "type": "processing_error"
            })
            return {"text": f"Error: {str(e)}"}

    def print_conversation_log(self, user_id):
        if user_id in self.memory:
            logger.debug("Conversation log", extra={
                "user_id": user_id,
                "messages": list(self.memory[user_id]),
                "type": "conversation_log"
            })
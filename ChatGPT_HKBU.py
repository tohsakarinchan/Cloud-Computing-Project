import configparser
import requests
import os
import random
from collections import defaultdict, deque
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

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
        return history

    def save_message_to_firestore(self, user_id, role, content):
        if not self.firestore_db:
            print("❗ Firestore 数据库未初始化，跳过写入。")
            return

        try:
            msg_ref = self.firestore_db.collection("chat_history").document(str(user_id)).collection("messages").document()
            msg_ref.set({
                "role": role,
                "content": content,
                "timestamp": SERVER_TIMESTAMP,
            })
            print(f"✅ Firestore 写入成功: {user_id} [{role}]")
        except Exception as e:
            print(f"❌ Firestore 写入失败: {e}")


    def try_fetch_vvquest_image(self, query, n=1):
        try:
            resp = requests.get("https://api.zvv.quest/search", params={"q": query, "n": n})
            if resp.status_code == 200:
                json_data = resp.json()
                if json_data.get("code") == 200 and json_data.get("data"):
                    return json_data["data"]
        except Exception as e:
            print(f"⚠️ VVQuest API Error: {e}")
        return []

    def submit(self, message, user_id=None):
        try:
            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            if not user_id:
                user_id = "anonymous"

            if user_id not in self.memory:
                self.memory[user_id] = deque(maxlen=5)
                try:
                    past = self.load_history_from_firestore(user_id, limit=5)
                    for msg in past:
                        self.memory[user_id].append(msg)
                except Exception as e:
                    print(f"⚠️ Firestore 加载失败: {e}")

            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.memory[user_id])
            messages.append({"role": "user", "content": message})

            payload = {"messages": messages}
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                content = response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")

                self.memory[user_id].append({"role": "user", "content": message})
                self.memory[user_id].append({"role": "assistant", "content": content})

                if self.firestore_db:
                    self.save_message_to_firestore(user_id, "user", message)
                    self.save_message_to_firestore(user_id, "assistant", content)

                # 60% 概率加入表情包图
                if random.random() < 0.6:
                    images = self.try_fetch_vvquest_image(query=message, n=1)
                    if images:
                        return {"text": content, "image_url": images[0]}

                return {"text": content}

            else:
                return {"text": f"Error: API request failed (Status Code: {response.status_code})"}

        except Exception as e:
            return {"text": f"Error: {str(e)}"}

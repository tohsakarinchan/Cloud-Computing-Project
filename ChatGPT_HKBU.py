import configparser
import requests
import os
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
            "你偶尔会用一些日语词汇回复，也会偶尔用一些颜文字。"
            "不要太客气，也不要太机械。尽可能展现出你的个性和情绪。"
        )

        # memory 只缓存最新 5 条上下文（role+message）
        self.memory = defaultdict(lambda: deque(maxlen=5))
        self.firestore_db = firestore_db

    def load_history_from_firestore(self, user_id, limit=5):
        """从 Firestore 加载历史对话"""
        context_ref = self.firestore_db.collection("chat_history").document(str(user_id)).collection("messages")
        query = context_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()

        history = []
        for doc in reversed(list(docs)):  # 倒序恢复为正序
            data = doc.to_dict()
            role = data.get("role", "user")
            content = data.get("content", "")
            history.append({"role": role, "content": content})
        
        return history

    def save_message_to_firestore(self, user_id, role, content):
        """将单条消息保存到 Firestore（新结构）"""
        msg_ref = self.firestore_db.collection("chat_history").document(str(user_id)).collection("messages").document()
        msg_ref.set({
            "role": role,
            "content": content,
            "timestamp": SERVER_TIMESTAMP,
        })

    def submit(self, message, user_id=None):
        try:
            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            if not user_id:
                user_id = "anonymous"

            # 如果是第一次对话，尝试加载历史
            if user_id not in self.memory:
                self.memory[user_id] = deque(maxlen=5)
                try:
                    past = self.load_history_from_firestore(user_id, limit=5)
                    for msg in past:
                        self.memory[user_id].append(msg)
                    print(f"📦 恢复了用户 {user_id} 的历史 {len(past)} 条记录")
                except Exception as e:
                    print(f"⚠️ Firestore 加载失败: {e}")

            # 构造消息历史
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.memory[user_id])
            messages.append({"role": "user", "content": message})

            payload = {"messages": messages}
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                content = response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")

                # 保存到内存
                self.memory[user_id].append({"role": "user", "content": message})
                self.memory[user_id].append({"role": "assistant", "content": content})

                # 保存到 Firestore
                if self.firestore_db:
                    self.save_message_to_firestore(user_id, "user", message)
                    self.save_message_to_firestore(user_id, "assistant", content)

                return content
            else:
                return f"Error: API request failed (Status Code: {response.status_code})"

        except Exception as e:
            return f"Error: {str(e)}"

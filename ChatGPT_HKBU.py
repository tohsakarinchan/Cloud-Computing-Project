import configparser
import requests
import os
from collections import defaultdict, deque
from google.cloud import firestore

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
            "不要太客气，也不要太机械。尽可能展现出你的个性和情绪。"
        )

        self.memory = defaultdict(lambda: deque(maxlen=5))
        self.firestore_db = firestore_db

    def submit(self, message, user_id=None):
        try:
            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            # 构造消息历史
            messages = [{"role": "system", "content": self.system_prompt}]
            if user_id and user_id in self.memory:
                messages.extend(self.memory[user_id])
            messages.append({"role": "user", "content": message})

            payload = {"messages": messages}
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                content = response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")

                # 记录到内存
                if user_id:
                    self.memory[user_id].append({"role": "user", "content": message})
                    self.memory[user_id].append({"role": "assistant", "content": content})

                    # 保存到 Firestore
                    if self.firestore_db:
                        self.save_to_firestore(user_id, message, content)

                return content
            else:
                return f"Error: API request failed (Status Code: {response.status_code})"

        except Exception as e:
            return f"Error: {str(e)}"

    def save_to_firestore(self, user_id, user_message, bot_reply):
        doc_ref = self.firestore_db.collection("chat_history").document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            history = data.get("history", [])
        else:
            history = []

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply})

        # 限制历史长度（比如只保留最近 50 条）
        if len(history) > 50:
            history = history[-50:]

        doc_ref.set({"history": history}, merge=True)

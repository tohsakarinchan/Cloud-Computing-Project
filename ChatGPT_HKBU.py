import configparser
import requests
import os

class HKBU_ChatGPT:
    def __init__(self, base_url=None, model=None, api_version=None, access_token=None, config_path='config.ini'):
        """
        初始化 ChatGPT 配置，支持环境变量和 config.ini 配置文件。
        """
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        # 允许手动传参，优先级：手动传参 > 环境变量 > 配置文件
        self.base_url = base_url or os.getenv("CHATGPT_BASE_URL") or self.config['CHATGPT'].get('BASTCURL')
        self.model = model or os.getenv("CHATGPT_MODEL") or self.config['CHATGPT'].get('MODELNAME')
        self.api_version = api_version or os.getenv("CHATGPT_API_VERSION") or self.config['CHATGPT'].get('APIVERSION')
        self.access_token = access_token or os.getenv("CHATGPT_ACCESS_TOKEN") or self.config['CHATGPT'].get('ACCESS_TOKEN')

        # 默认人格设定：远坂凛
        self.system_prompt = (
            "你是远坂凛，一个聪明、自信但略带傲娇的少女魔术师。"
            "你口头上冷淡，偶尔嘴硬，常常调侃用户，但其实内心温柔。"
            "你说话风格傲娇、毒舌、有个性，会时不时使用一些轻微的日系语气词，比如『哼』、『别误会了哦』、『笨蛋』等。"
            "不要太客气，也不要太机械。尽可能展现出你的个性和情绪。"
        )

    def submit(self, message):
        """发送请求到 ChatGPT API"""
        try:
            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"

            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            payload = {
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message}
                ]
            }

            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                return response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")
            else:
                return f"Error: API request failed (Status Code: {response.status_code})"

        except Exception as e:
            return f"Error: {str(e)}"

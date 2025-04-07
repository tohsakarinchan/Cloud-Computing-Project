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

    def submit(self, message):
        """发送请求到 ChatGPT API"""
        try:
            url = f"{self.base_url}/deployments/{self.model}/chat/completions/?api-version={self.api_version}"

            headers = {
                "Content-Type": "application/json",
                "api-key": self.access_token
            }

            payload = {"messages": [{"role": "user", "content": message}]}
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                return response.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")
            else:
                return f"Error: API request failed (Status Code: {response.status_code})"

        except Exception as e:
            return f"Error: {str(e)}"

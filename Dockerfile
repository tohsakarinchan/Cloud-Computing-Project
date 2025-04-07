FROM python:3.9

# 设置工作目录
WORKDIR /app

# 拷贝项目代码
COPY . .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 启动入口
CMD ["python", "chatbot.py"]

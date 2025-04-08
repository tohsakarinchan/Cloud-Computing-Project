# 使用官方 Python 运行时作为父镜像
FROM python:3.9

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt ./

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 默认端口（Cloud Run 默认监听 8080）
EXPOSE 8080

# 启动命令
CMD ["python", "chatbot_quart.py"]

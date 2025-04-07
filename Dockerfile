FROM python:3.9

# 设置工作目录
WORKDIR /app

# 拷贝代码文件
COPY . .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量用于认证 Firestore
ENV GOOGLE_APPLICATION_CREDENTIALS="/app/firebase_key.json"

# 运行你的应用（替换成实际入口）
CMD ["python", "app.py"]

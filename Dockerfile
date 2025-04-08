# 使用官方 Python 轻量镜像（兼容 Cloud Run）
FROM python:3.9-slim as builder

# 安装编译依赖（如需）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- 运行时阶段 ---
FROM python:3.9-slim

# 设置非 root 用户（GCP 非强制但推荐）
RUN useradd -m appuser && \
    mkdir -p /app && \
    chown appuser:appuser /app
USER appuser
WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /home/appuser/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

# 确保 PATH 包含用户级 pip 安装路径
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=8080 

# 暴露端口（与 Cloud Run 的 $PORT 一致）
EXPOSE $PORT

# 健康检查（Cloud Run 自动监控）
HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:$PORT/ || exit 1

# 启动命令（确保您的 Quart 应用监听 $PORT）
CMD ["python", "chatbot_quart.py"]
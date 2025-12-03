FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 清理apt缓存（保持镜像精简）
RUN apt-get update && apt-get clean && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY auto_ddns.py .

# 创建日志目录
RUN mkdir -p /app/logs

# 设置可执行权限
RUN chmod +x auto_ddns.py

# 默认命令（可以通过docker run覆盖）
CMD ["python3", "auto_ddns.py"]


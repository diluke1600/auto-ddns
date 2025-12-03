# 自动DDNS脚本

自动获取公网IP地址并更新到阿里云DNS的Python脚本。

## 功能特性

- 自动获取当前公网IP地址（支持多个IP服务作为备选）
- 自动更新阿里云DNS记录
- 如果记录不存在，自动创建新记录
- 如果IP未变化，跳过更新
- 详细的日志记录
- 飞书Webhook通知（卡片格式，无论是否更新都通知）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

1. 复制配置文件模板：
```bash
cp config.json.example config.json
```

2. 编辑 `config.json`，填入你的配置信息：
```json
{
    "access_key_id": "your_access_key_id",
    "access_key_secret": "your_access_key_secret",
    "domain": "ai.uih-devops.com",
    "feishu_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
}
```

### 获取阿里云AccessKey

1. 登录阿里云控制台
2. 进入 [AccessKey管理页面](https://ram.console.aliyun.com/manage/ak)
3. 创建AccessKey，获取AccessKey ID和AccessKey Secret

**注意**：为了安全，建议创建一个具有DNS管理权限的子账号，而不是使用主账号的AccessKey。

### 配置飞书Webhook（可选）

1. 在飞书群聊中，点击右上角设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 设置机器人名称和描述
3. 复制Webhook地址
4. 将Webhook地址填入配置文件的 `feishu_webhook_url` 字段

**注意**：
- 如果不配置 `feishu_webhook_url`，脚本会正常运行但不会发送通知
- 通知使用卡片格式，包含域名、IP地址、更新状态等信息
- 无论IP是否更新，都会发送通知（包括"无需更新"的情况）

## 使用方法

### 方式一：直接运行（Python）

#### 手动运行

```bash
python3 auto_ddns.py
```

#### 定时任务（crontab）

编辑crontab：
```bash
crontab -e
```

添加以下行（每10分钟执行一次）：
```
*/10 * * * * cd /home/huamaolin/workspace/auto-ddns && /usr/bin/python3 auto_ddns.py >> /dev/null 2>&1
```

或者使用systemd定时器（推荐）。

### 方式二：Docker运行（推荐）

#### 构建镜像

```bash
docker build -t auto-ddns:latest .
```

#### 运行容器（单次执行）

```bash
docker run --rm \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/logs:/app/logs \
  auto-ddns:latest
```

#### 使用Docker Compose

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### Docker定时执行

**方案1：使用外部cron（推荐）**

在宿主机上设置crontab，定时执行docker命令：
```bash
crontab -e
```

添加：
```
*/10 * * * * docker run --rm -v /path/to/auto-ddns/config.json:/app/config.json:ro -v /path/to/auto-ddns/logs:/app/logs auto-ddns:latest
```

**方案2：使用包含cron的容器**

如果需要容器内定时执行，可以使用以下Dockerfile（需要额外安装cron）：
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auto_ddns.py .

# 创建cron任务
RUN echo "*/10 * * * * cd /app && python3 auto_ddns.py >> /var/log/cron.log 2>&1" > /etc/cron.d/ddns-cron
RUN chmod 0644 /etc/cron.d/ddns-cron
RUN crontab /etc/cron.d/ddns-cron

CMD ["cron", "-f"]
```

**方案3：使用docker-compose的restart策略**

在`docker-compose.yml`中设置restart策略，配合外部调度工具（如Kubernetes CronJob）使用。

## Docker构建说明

### 标准Dockerfile

使用 `Dockerfile` 构建的镜像只执行一次脚本，适合配合外部cron使用。

### 带Cron的Dockerfile

使用 `Dockerfile.cron` 构建的镜像包含cron服务，会在容器内定时执行：

```bash
docker build -f Dockerfile.cron -t auto-ddns:cron .
docker run -d --name auto-ddns \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/logs:/app/logs \
  auto-ddns:cron
```

## 日志

脚本运行日志会同时输出到：
- 控制台（stdout）
- 日志文件 `ddns.log`（直接运行时）
- Docker日志（使用docker logs查看）

## 注意事项

1. 确保你的阿里云账号有对应域名的DNS管理权限
2. 确保域名 `uih-devops.com` 已经在阿里云DNS中解析
3. 脚本会自动创建或更新 `ai.uih-devops.com` 的A记录
4. 默认TTL设置为600秒（10分钟）

## 飞书通知说明

脚本支持通过飞书Webhook发送卡片格式的通知，通知内容包括：

- **域名**：当前更新的域名
- **当前IP**：获取到的公网IP地址
- **旧IP**：如果IP发生变化，显示旧IP地址
- **状态**：更新状态（成功/已更新/无需更新/失败）
- **更新时间**：操作时间戳

通知会在以下情况发送：
- ✅ DNS记录创建成功
- 🔄 DNS记录更新成功（IP变化）
- ℹ️ IP未变化，无需更新
- ❌ DNS操作失败

## 故障排查

1. **无法获取IP地址**：检查网络连接，脚本会尝试多个IP服务
2. **DNS更新失败**：检查AccessKey权限和域名配置
3. **飞书通知失败**：检查Webhook URL是否正确，网络是否可达
4. **查看详细日志**：检查 `ddns.log` 文件


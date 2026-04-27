# Docker Compose 部署

适合 1C / 1G / 25G 小 VPS。默认配置会把状态、账号 token、缓存放在宿主机当前目录的 `./data`。

## 1. 安装 Docker

如果 VPS 已经有 Docker 和 Compose，可跳过。

Debian/Ubuntu 常见安装方式：

```bash
apt update
apt install -y docker.io docker-compose-v2 git
systemctl enable --now docker
```

如果你的系统包里没有 `docker-compose-v2`，也可以使用 Docker 官方安装脚本或安装 `docker-compose-plugin`。

## 2. 拉代码

```bash
cd /opt
git clone https://github.com/wuuduf/claw-wechat-parser.git
cd /opt/claw-wechat-parser
```

## 3. 可选：编辑配置

```bash
cp .env.example .env
nano .env
```

小 VPS 推荐保持默认：

```env
PUID=0
PGID=0
CLAW_PARSER_MAX_MEDIA_SIZE_MB=60
CLAW_PARSER_MAX_MEDIA_DURATION_S=600
CLAW_PARSER_CACHE_MAX_GB=4
```

默认使用 `PUID=0`/`PGID=0` 是为了避免 bind mount 的 `./data` 目录权限问题，减少小 VPS 首次部署步骤。如果你要改成非 root 用户，需要先创建并授权数据目录，例如：

```bash
mkdir -p data
chown -R 10001:10001 data
```

如果某个平台需要 Cookie，再填对应变量。

## 4. 构建镜像

```bash
docker compose build
```

## 5. 微信扫码登录

```bash
docker compose run --rm claw-parser login-wechat
```

终端会显示二维码和链接。扫码确认后，账号凭据会保存到：

```text
/opt/claw-wechat-parser/data/accounts/
```

## 6. 后台启动

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

更新：

```bash
cd /opt/claw-wechat-parser
git pull
docker compose build
docker compose up -d
```

## 常用命令

本地解析测试：

```bash
docker compose run --rm claw-parser parse 'https://www.bilibili.com/video/BV1xx411c7mD'
```

查看账号：

```bash
docker compose run --rm claw-parser accounts list
```

重新扫码：

```bash
docker compose run --rm claw-parser login-wechat
```

## 注意

- 本项目不需要开放端口。
- `./data` 目录包含微信 token 和平台 cookie，注意备份和权限。
- 如果磁盘紧张，可以删除缓存：

```bash
rm -rf /opt/claw-wechat-parser/data/cache/*
docker compose restart
```

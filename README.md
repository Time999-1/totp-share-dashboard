# 车友 2FA 验证码看板

一个可私有部署的 TOTP 分享看板。管理员录入车辆名称、编号和 2FA Base32 密钥，系统每 30 秒生成新的六位验证码，并为每辆车创建独立、不可猜测、可撤销的分享链接。

![界面预览](docs/ui-preview.png)

## 功能

- 单管理员登录
- 添加、编辑车辆名称与编号
- TOTP 六位验证码和 30 秒倒计时
- 每辆车独立分享链接
- 一键复制验证码和分享链接
- 停用、启用或重置分享链接
- 最近 300 条访问记录
- 2FA 密钥加密保存
- 登录及接口访问限速
- SQLite 持久化，无需额外数据库
- Docker Compose 一键部署

> 分享链接相当于第二重验证凭据。仅用于你有权管理的共享账号，不要公开传播。

## 在 1Panel 中部署

### 1. 准备项目

把整个项目上传到服务器，例如：

```text
/opt/1panel/apps/totp-share-dashboard
```

也可以将项目推送到自己的 GitHub/Gitee 仓库，然后在服务器拉取。

### 2. 创建环境文件

复制 `.env.example` 为 `.env`，修改以下四项：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的强密码
SESSION_SECRET=至少32位随机字符串
APP_ENCRYPTION_KEY=至少32位随机字符串
```

可在服务器生成随机字符串：

```bash
openssl rand -hex 32
```

`APP_ENCRYPTION_KEY` 部署后不要随意修改，否则数据库里的 2FA 密钥将无法解密。

### 3. 创建 Compose 编排

进入 1Panel：

```text
容器 → 编排 → 创建编排
```

选择项目目录中的 `docker-compose.yml`，然后启动。服务默认只监听服务器本机：

```text
127.0.0.1:8787
```

### 4. 创建网站和反向代理

进入：

```text
网站 → 创建网站 → 反向代理
```

代理地址填写：

```text
http://127.0.0.1:8787
```

绑定自己的域名并申请 HTTPS 证书。必须使用 HTTPS，否则浏览器的复制功能和 Cookie 安全策略可能无法正常工作。

### 5. 登录

打开：

```text
https://你的域名/login
```

使用 `.env` 中设置的管理员账号和密码登录。

## 更新项目

如果项目来自 Git 仓库：

```bash
git pull
docker compose up -d --build
```

数据库存放在 Docker 数据卷 `totp_data` 中，重新构建容器不会丢失。

## 备份

需要备份两个内容：

```text
.env
Docker 数据卷中的 totp.db
```

导出数据库：

```bash
docker cp totp-share-dashboard:/app/data/totp.db ./totp.db.backup
```

恢复时先停止容器，再把备份复制回去：

```bash
docker compose stop
docker cp ./totp.db.backup totp-share-dashboard:/app/data/totp.db
docker compose start
```

两者缺一不可。数据库包含加密后的密钥，`.env` 包含解密所需的 `APP_ENCRYPTION_KEY`。

## 本地运行

```bash
cp .env.example .env
# 修改 .env 中的密码和随机字符串
docker compose up -d --build
```

访问 `http://127.0.0.1:8787`。如果只在本机使用 HTTP 测试，可暂时在 `.env` 设置：

```env
COOKIE_SECURE=false
```

正式部署必须改回 `true`。

## 安全说明

- 分享链接使用高强度随机令牌，并可随时重置。
- 2FA 密钥通过 Fernet 对称加密后保存。
- 浏览器只取得当前验证码，不会取得 2FA 原始密钥。
- 管理后台和分享页均禁止搜索引擎收录。
- 建议定期检查访问记录，链接泄露后立即重置。
- 更高安全要求可在 1Panel/Nginx 中增加 IP 白名单或额外访问认证。

## 技术栈

- Python / Flask
- pyotp
- SQLite
- Gunicorn
- Docker Compose

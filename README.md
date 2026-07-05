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

## 一键部署（推荐）

服务器需要已经安装 Git、Docker、Docker Compose、OpenSSL 和 curl，并使用 `root` 用户执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Time999-1/totp-share-dashboard/main/install.sh -o /tmp/install-totp-dashboard.sh \
  && bash /tmp/install-totp-dashboard.sh
```

脚本会自动完成：

- 拉取或更新项目到 `/opt/totp-share-dashboard`
- 首次安装时生成管理员密码和两个随机安全密钥
- 保留已有 `.env`、数据库和加密密钥
- 构建并启动 Docker Compose
- 等待并检查 `/health`

部署完成后，脚本不会直接显示密码。查看首次安装生成的管理员密码：

```bash
sudo cat /root/totp-share-dashboard-admin-password.txt
```

管理员账号默认为 `admin`。记录密码后建议删除明文密码文件：

```bash
sudo rm -f /root/totp-share-dashboard-admin-password.txt
```

然后在 1Panel 创建反向代理，目标填写：

```text
http://127.0.0.1:8787
```

绑定域名并开启 HTTPS 后，通过 `https://你的域名/login` 登录。

### 修改或忘记管理员密码

网站首次启动后，管理员密码已经加密写入数据库。此时只修改 `.env` 中的 `ADMIN_PASSWORD` **不会生效**。请执行：

```bash
cd /opt/totp-share-dashboard
docker compose exec totp-dashboard flask --app app reset-admin-password
```

根据提示输入两遍新密码。输入过程不会显示字符，密码至少需要 12 位。修改后无需重启容器。

### 一键更新

重新执行一键部署命令即可。脚本会执行 `git pull` 和重新构建，同时保留 `.env` 与数据库：

```bash
curl -fsSL https://raw.githubusercontent.com/Time999-1/totp-share-dashboard/main/install.sh -o /tmp/install-totp-dashboard.sh \
  && bash /tmp/install-totp-dashboard.sh
```

## 推荐部署：SSH 启动 + 1Panel 反向代理

以下方式已经实际验证。SSH 负责启动 Docker Compose，1Panel 只负责域名、反向代理和 HTTPS。不要再在 1Panel 中重复创建同一个 Compose 编排。

### 1. 检查环境

```bash
git --version
docker --version
docker compose version
```

### 2. 拉取项目

```bash
cd /opt
git clone https://github.com/Time999-1/totp-share-dashboard.git
cd totp-share-dashboard
```

如果目录已经存在，不要再次克隆，使用：

```bash
cd /opt/totp-share-dashboard
git pull
```

### 3. 创建安全配置

复制环境文件，并直接生成两个不会显示在终端里的随机密钥：

```bash
cp .env.example .env
sed -i "s/^SESSION_SECRET=.*/SESSION_SECRET=$(openssl rand -hex 32)/" .env
sed -i "s/^APP_ENCRYPTION_KEY=.*/APP_ENCRYPTION_KEY=$(openssl rand -hex 32)/" .env
nano .env
```

在编辑器中只需设置管理员账号和强密码，并确认正式部署使用安全 Cookie：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的强密码
COOKIE_SECURE=true
```

Nano 保存方法：按 `Ctrl+O`、回车，再按 `Ctrl+X`。不要截图、发送或提交 `.env`。

`APP_ENCRYPTION_KEY` 部署后不要修改，否则数据库里的 2FA 密钥将无法解密。

### 4. 启动并检查

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8787/health
```

健康检查应返回：

```text
{"status":"ok"}
```

服务只监听服务器本机：

```text
127.0.0.1:8787
```

### 5. 在 1Panel 创建反向代理

进入：

```text
网站 → 创建网站 → 反向代理
```

代理地址填写：

```text
http://127.0.0.1:8787
```

绑定自己的域名并申请 HTTPS 证书。必须使用 HTTPS，否则浏览器的复制功能和 Cookie 安全策略可能无法正常工作。

### 6. 登录

打开：

```text
https://你的域名/login
```

使用 `.env` 中设置的管理员账号和密码登录。

### 可选：完全使用 1Panel 编排

也可以不执行 `docker compose up -d --build`，改为在 1Panel 中选择项目目录的 `docker-compose.yml` 创建编排。两种启动方式二选一，不要重复部署。

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

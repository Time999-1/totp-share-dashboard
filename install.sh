#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Time999-1/totp-share-dashboard.git"
INSTALL_DIR="${INSTALL_DIR:-/opt/totp-share-dashboard}"
PASSWORD_FILE="/root/totp-share-dashboard-admin-password.txt"

info() { printf '\033[1;32m[INFO]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 root 用户运行此脚本。"
fi

for command_name in git docker openssl curl; do
  command -v "${command_name}" >/dev/null 2>&1 || fail "缺少命令: ${command_name}"
done
docker compose version >/dev/null 2>&1 || fail "未检测到 Docker Compose 插件。"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  info "检测到已有项目，正在更新代码……"
  git -C "${INSTALL_DIR}" pull --ff-only
elif [[ -e "${INSTALL_DIR}" ]]; then
  fail "${INSTALL_DIR} 已存在但不是 Git 仓库，请先检查或更换 INSTALL_DIR。"
else
  info "正在拉取项目……"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

install -m 755 "${INSTALL_DIR}/manage.sh" /usr/local/bin/totp-dashboard

if [[ ! -f .env ]]; then
  info "正在生成安全配置……"
  umask 077
  admin_password="$(openssl rand -hex 12)"
  session_secret="$(openssl rand -hex 32)"
  encryption_key="$(openssl rand -hex 32)"
  {
    printf 'ADMIN_USERNAME=admin\n'
    printf 'ADMIN_PASSWORD=%s\n' "${admin_password}"
    printf 'SESSION_SECRET=%s\n' "${session_secret}"
    printf 'APP_ENCRYPTION_KEY=%s\n' "${encryption_key}"
    printf 'TRUST_PROXY=true\n'
    printf 'COOKIE_SECURE=true\n'
    printf 'TZ=Asia/Shanghai\n'
  } > .env
  printf '%s\n' "${admin_password}" > "${PASSWORD_FILE}"
  chmod 600 .env "${PASSWORD_FILE}"
  unset admin_password session_secret encryption_key
else
  info "检测到已有 .env，将保留原有密码和加密密钥。"
fi

info "正在构建并启动容器……"
docker compose up -d --build

info "等待健康检查……"
healthy=false
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8787/health >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "${healthy}" != "true" ]]; then
  docker compose ps
  fail "服务未在预期时间内通过健康检查，请运行 docker compose logs --tail=100 查看日志。"
fi

docker compose ps
printf '\n'
info "部署成功。"
printf '本机地址: http://127.0.0.1:8787\n'
if [[ -f "${PASSWORD_FILE}" ]]; then
  printf '初始管理员账号: admin\n'
  printf '查看初始密码: sudo cat %s\n' "${PASSWORD_FILE}"
fi
printf '下一步: 在 1Panel 创建反向代理，目标填写 http://127.0.0.1:8787，并启用 HTTPS。\n'
printf '管理命令: sudo totp-dashboard help\n'

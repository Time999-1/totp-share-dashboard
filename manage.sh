#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/totp-share-dashboard}"
PASSWORD_FILE="${PASSWORD_FILE:-/root/totp-share-dashboard-admin-password.txt}"

info() { printf '\033[1;32m[INFO]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

wait_for_health() {
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8787/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 root 用户运行：sudo totp-dashboard $*"
fi

[[ -f "${INSTALL_DIR}/docker-compose.yml" ]] || fail "未找到项目：${INSTALL_DIR}"
cd "${INSTALL_DIR}"

case "${1:-help}" in
  status)
    docker compose ps
    ;;
  update)
    info "更新代码并重新构建……"
    git pull --ff-only
    docker compose up -d --build
    info "等待服务健康检查……"
    wait_for_health || fail "服务未通过健康检查，请运行 totp-dashboard logs 查看日志。"
    info "更新完成。"
    ;;
  password)
    docker compose exec totp-dashboard flask --app app reset-admin-password
    ;;
  initial-password)
    [[ -f "${PASSWORD_FILE}" ]] || fail "初始密码文件不存在；如已删除，请使用 password 重设密码。"
    cat "${PASSWORD_FILE}"
    ;;
  logs)
    docker compose logs --tail="${2:-100}" -f
    ;;
  restart)
    docker compose restart
    ;;
  help|-h|--help)
    cat <<'EOF'
用法：sudo totp-dashboard <命令>

  status             查看运行状态
  update             拉取新版并重新构建
  password           修改管理员密码
  initial-password   查看首次安装生成的初始密码
  logs [行数]        查看实时日志，默认最近 100 行
  restart            重启服务
  help               显示本帮助
EOF
    ;;
  *)
    fail "未知命令：$1。运行 totp-dashboard help 查看帮助。"
    ;;
esac

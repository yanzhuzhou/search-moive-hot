#!/bin/bash
# 一键启动：虚拟显示器 + VNC + noVNC 网页 + 价格采集工具服务
# 用法: bash start_vnc.sh
set -e

DISPLAY_NUM=42
VNC_PORT=5901
NOVNC_PORT=6080
APP_PORT=8000

echo "========================================"
echo "  价格采集工具 - noVNC 远程登录环境启动"
echo "========================================"
echo

# 1. 启动 Xvfb 虚拟显示器
if ! pgrep -f "Xvfb :${DISPLAY_NUM}" > /dev/null 2>&1; then
    echo "[1/4] 启动 Xvfb 虚拟显示器 :${DISPLAY_NUM}..."
    mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
    Xvfb :${DISPLAY_NUM} -screen 0 1280x800x24 -ac -nolisten tcp > /dev/null 2>&1 &
    sleep 2
    if DISPLAY=:${DISPLAY_NUM} xdpyinfo > /dev/null 2>&1; then
        echo "  ✓ Xvfb 已启动"
    else
        echo "  ✗ Xvfb 启动失败"
        exit 1
    fi
else
    echo "[1/4] Xvfb :${DISPLAY_NUM} 已在运行"
fi
export DISPLAY=:${DISPLAY_NUM}

# 2. 启动 x11vnc
if ! pgrep -f "x11vnc.*:${DISPLAY_NUM}" > /dev/null 2>&1; then
    echo "[2/4] 启动 x11vnc (端口 ${VNC_PORT})..."
    x11vnc -display :${DISPLAY_NUM} -forever -shared -nopw \
           -listen 0.0.0.0 -rfbport ${VNC_PORT} > /dev/null 2>&1 &
    sleep 1
    if pgrep -f "x11vnc.*:${DISPLAY_NUM}" > /dev/null 2>&1; then
        echo "  ✓ x11vnc 已启动"
    else
        echo "  ✗ x11vnc 启动失败"
        exit 1
    fi
else
    echo "[2/4] x11vnc 已在运行"
fi

# 3. 启动 websockify (noVNC 网页)
if ! pgrep -f "websockify.*${NOVNC_PORT}" > /dev/null 2>&1; then
    echo "[3/4] 启动 noVNC 网页 (端口 ${NOVNC_PORT})..."
    websockify --web /usr/share/novnc 0.0.0.0:${NOVNC_PORT} localhost:${VNC_PORT} > /dev/null 2>&1 &
    sleep 1
    if pgrep -f "websockify.*${NOVNC_PORT}" > /dev/null 2>&1; then
        echo "  ✓ noVNC 已启动"
    else
        echo "  ✗ noVNC 启动失败"
        exit 1
    fi
else
    echo "[3/4] noVNC 已在运行"
fi

# 4. 启动价格采集工具服务
echo "[4/4] 启动价格采集工具服务 (端口 ${APP_PORT})..."
echo
echo "========================================"
echo "  全部就绪！请按以下步骤操作："
echo "========================================"
echo
echo "1. 浏览器打开 noVNC 远程桌面:"
echo "   http://<沙箱地址>:${NOVNC_PORT}/vnc.html"
echo "   （左边栏点 Connect，无需密码）"
echo
echo "2. 在另一个终端窗口执行登录命令:"
echo "   cd /workspace/price_compare"
echo "   DISPLAY=:${DISPLAY_NUM} python3 -m price_compare.cli login jd"
echo "   （京东会弹出登录页，在 noVNC 窗口里扫码登录）"
echo
echo "3. 登录成功后采集真实数据:"
echo "   DISPLAY=:${DISPLAY_NUM} python3 -m price_compare.cli search 无线鼠标 --scraper playwright --real"
echo
echo "4. 或用网页界面操作:"
echo "   http://<沙箱地址>:${APP_PORT}/"
echo
echo "----------------------------------------"
echo "noVNC 桌面 :  http://<沙箱地址>:${NOVNC_PORT}/vnc.html"
echo "采集工具页 :  http://<沙箱地址>:${APP_PORT}/"
echo "----------------------------------------"
echo
exec python3 server.py --host 0.0.0.0 --port ${APP_PORT}

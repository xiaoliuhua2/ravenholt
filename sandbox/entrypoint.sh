#!/bin/bash
# ============================================================
# Ravenholt 一体化沙箱镜像入口
#
# 顺序是有意的：
#   1) 先把 Ravenholt 附加服务（桌面栈 + Go 控制面）用 supervisord 挂到后台 ——
#      它们不依赖 Caido，先起可让 noVNC / 容器控制台尽早可用；
#   2) 再把控制权交给 strix 上游 docker-entrypoint.sh —— 它负责启动 Caido、
#      等待 API 就绪、写全局代理环境与浏览器 CA，最后 exec "$@" 保持容器存活。
#
# 这样上游脚本的演进（新增 Caido 参数等）会被自动继承，无需在此复制它的实现。
# ============================================================
set -eu

# chromium 的 user-data-dir（supervisord.conf 里用 --user-data-dir=/data）：
# 上游 entrypoint 不创建它，这里补上并交给 pentester。
mkdir -p /data 2>/dev/null || sudo mkdir -p /data
chown -R pentester:pentester /data 2>/dev/null || sudo chown -R pentester:pentester /data

# supervisord 需要 root 才能跑 Xvfb / x11vnc / 监听控制面端口；
# 上游镜像里 pentester 具备免密 sudo（其 entrypoint 同样依赖这一点）。
sudo supervisord -c /etc/ravenholt/supervisord.conf >>/tmp/ravenholt-supervisord.log 2>&1 &

echo "ravenholt: 附加服务已挂到后台（supervisord）；移交上游 entrypoint 启动 Caido"
exec /usr/local/bin/docker-entrypoint.sh "$@"

"""本机 SearXNG 的自动保障（best-effort）。

为什么存在：SearXNG 是「零配置就能用」的联网检索后端，不该要求部署者手工维护容器
生命周期。本模块在**服务启动时**把本机 SearXNG 拉起来：

1. 只处理 ``base_url`` 指向**本机**（``127.0.0.1`` / ``localhost`` / ``::1``）的情况；
2. 先探活——可达就直接返回，什么都不做；
3. 不可达 → 容器已存在则 ``docker start``；不存在则写好 settings 后 ``docker run``
   （镜像缺失先 ``pull``，带镜像源回退）；
4. **任何一步失败只记日志，绝不阻断服务启动**（检索侧还有无 key 安全数据库兜底）。

关闭：环境变量 ``RAVENHOLT_SEARXNG_AUTOPROVISION=0``。
"""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import requests


logger = logging.getLogger(__name__)

CONTAINER_NAME = "searxng"
SETTINGS_PATH = Path("/opt/searxng/settings.yml")
CONTAINER_PORT = 8080
# 依次尝试：国内可达的镜像源在前，官方 Docker Hub 在后（本部署实测 Hub 被墙）
IMAGE_CANDIDATES = (
    "docker.m.daocloud.io/searxng/searxng:latest",
    "dockerproxy.net/searxng/searxng:latest",
    "searxng/searxng:latest",
)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

# 只保留在本网络内实测可达的引擎（Google/DuckDuckGo/Bing 等被墙或触发验证码）。
# 注意：必须用「逐个禁用」而非 keep_only——keep_only 会让默认分类选不到任何引擎。
_SETTINGS_TEMPLATE = """use_default_settings: true
server:
  secret_key: "{secret}"
  limiter: false
  image_proxy: false
  public_instance: false
search:
  safe_search: 0
  default_lang: all
  formats:
    - html
    - json
engines:
  - name: yandex
    disabled: false
  - name: sogou
    disabled: false
  - name: naver
    disabled: false
  - name: 360search
    disabled: false
  - name: google
    disabled: true
  - name: duckduckgo
    disabled: true
  - name: brave
    disabled: true
  - name: google cse
    disabled: true
  - name: wikipedia
    disabled: true
  - name: wikidata
    disabled: true
  - name: baidu
    disabled: true
  - name: mojeek
    disabled: true
  - name: yep
    disabled: true
  - name: qwant
    disabled: true
  - name: startpage
    disabled: true
  - name: yahoo
    disabled: true
"""


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:  # noqa: BLE001 - docker 不可用等一律按失败处理
        logger.debug("searxng provision: command failed: %s", " ".join(args), exc_info=True)
        return None


def _reachable(base_url: str, timeout: float = 4.0) -> bool:
    url = base_url.rstrip("/") + "/"
    try:
        response = requests.get(url, timeout=timeout)
        # 200/302/405/400 都说明 HTTP 服务在；连接被拒/超时才是"没起来"
        return response.status_code < 500
    except requests.exceptions.RequestException:
        return False


def _write_settings() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS_PATH.exists():
        return
    SETTINGS_PATH.write_text(
        _SETTINGS_TEMPLATE.format(secret=secrets.token_urlsafe(32)), encoding="utf-8"
    )
    logger.info("searxng provision: 已写入 %s", SETTINGS_PATH)


def _container_exists() -> bool:
    result = _run(["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME], timeout=20)
    return bool(result and result.returncode == 0)


def _image_present(image: str) -> bool:
    result = _run(["docker", "image", "inspect", image], timeout=20)
    return bool(result and result.returncode == 0)


def _ensure_image() -> str | None:
    for image in IMAGE_CANDIDATES:
        if _image_present(image):
            return image
    for image in IMAGE_CANDIDATES:
        logger.info("searxng provision: 拉取镜像 %s", image)
        result = _run(["docker", "pull", image], timeout=600)
        if result and result.returncode == 0:
            return image
        logger.warning("searxng provision: 镜像 %s 拉取失败", image)
    return None


def _run_container(base_url: str, bind_addr: str) -> bool:
    _write_settings()
    image = _ensure_image()
    if image is None:
        logger.warning("searxng provision: 无可用镜像，放弃自动创建")
        return False
    port = urlsplit(base_url).port or 8888
    # 端口发布的宿主绑定地址由 ``searxng_bind_addr`` 决定，默认 0.0.0.0：
    # 沙箱容器在 macvlan 上有独立 IP（经宿主 LAN IP 访问）或回退 bridge（经 docker
    # 网关 172.17.0.1 访问），只绑 loopback 时沙箱侧一律连不上。公网部署应把它改成
    # 127.0.0.1 或宿主内网 IP —— 该服务无鉴权，绑公网接口等于开放检索代理。
    args = [
        "docker", "run", "-d", "--name", CONTAINER_NAME, "--restart", "unless-stopped",
        "-p", f"{bind_addr}:{port}:{CONTAINER_PORT}",
        "-v", f"{SETTINGS_PATH}:/etc/searxng/settings.yml:ro",
        "-e", f"SEARXNG_BASE_URL={base_url.rstrip('/')}/",
        image,
    ]
    result = _run(args, timeout=180)
    ok = bool(result and result.returncode == 0)
    logger.info("searxng provision: 容器创建%s", "成功" if ok else "失败")
    return ok


def ensure_local_searxng(
    base_url: str,
    *,
    enabled: bool | None = None,
    bind_addr: str = "0.0.0.0",
    attempts: int = 1,
) -> bool:
    """确保本机 SearXNG 可达；返回是否最终可用。**永不自阻断**。

    ``enabled=False``（控制台开关关掉）或环境变量
    ``RAVENHOLT_SEARXNG_AUTOPROVISION=0`` 时直接跳过，只做可达性判定不做容器操作。

    ``bind_addr`` 是新建容器时端口发布到的宿主地址（见 ``searxng_bind_addr`` 配置）：
    只做可达性判定；容器已存在时不动它的绑定，需要换绑请先 ``docker rm -f searxng``。
    """
    bind_addr = bind_addr.strip() or "0.0.0.0"
    if enabled is False:
        logger.info("searxng provision: 控制台已关闭自动保障（仅判定可达性）")
        return _reachable(base_url or "")
    if os.environ.get("RAVENHOLT_SEARXNG_AUTOPROVISION", "1").strip() in ("0", "false", "no"):
        logger.info("searxng provision: 已由环境变量关闭")
        return _reachable(base_url or "")

    url = (base_url or "").strip()
    if not url:
        return False
    host = (urlsplit(url).hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        logger.info("searxng provision: base_url 非本机（%s），跳过自动保障", host or "?")
        return False

    if _reachable(url):
        logger.info("searxng provision: 本机 SearXNG 已可达（%s%s）", url, "" if attempts == 1 else "")
        return True

    logger.warning("searxng provision: 本机 SearXNG 不可达 %s，尝试自动拉起", url)
    if _container_exists():
        logger.info("searxng provision: 容器已存在，执行 docker start")
        _run(["docker", "start", CONTAINER_NAME], timeout=120)
    elif not _run_container(url, bind_addr):
        return False

    # 容器刚起需要几秒初始化
    for _ in range(10):
        if _reachable(url):
            logger.info("searxng provision: 自动拉起成功（%s）", url)
            return True
        subprocess.run(["sleep", "2"], check=False)  # noqa: S603,S607 - 仅等待容器就绪
    logger.warning("searxng provision: 自动拉起后仍不可达（%s）", url)
    return False


__all__ = ["ensure_local_searxng", "SETTINGS_PATH", "CONTAINER_NAME"]

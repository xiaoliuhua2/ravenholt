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
import re
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

# 默认启用的通用引擎（本网络实测可达）。
# 下面这批是**被墙或触发验证码**的通用引擎，默认禁用；控制台开关
# ``integrations.searxng_general_engines`` 打开后把它们改成启用
# （见 :func:`apply_general_engines`）。
_GENERAL_ENGINES = ("google", "bing", "duckduckgo", "brave")

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
    disabled: {general_engines}
  - name: bing
    disabled: {general_engines}
  - name: duckduckgo
    disabled: {general_engines}
  - name: brave
    disabled: {general_engines}
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

_SECRET_RE = re.compile(r'^  secret_key:\s*"?([^"\n]+?)"?\s*$', re.M)


def _settings_text(secret: str, *, general_engines: bool) -> str:
    return _SETTINGS_TEMPLATE.format(
        secret=secret, general_engines="false" if general_engines else "true"
    )


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


def _write_settings(*, general_engines: bool) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS_PATH.exists():
        return
    SETTINGS_PATH.write_text(
        _settings_text(secrets.token_urlsafe(32), general_engines=general_engines),
        encoding="utf-8",
    )
    logger.info("searxng provision: 已写入 %s", SETTINGS_PATH)


def _existing_secret() -> str | None:
    try:
        text = SETTINGS_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _SECRET_RE.search(text)
    return match.group(1) if match else None


def _current_general_engines_enabled() -> bool | None:
    """读现有 settings.yml 判断这批通用引擎当前是否启用（全启用才算启用）。

    返回 ``None`` 表示这份文件里压根没有这批引擎的条目（例如部署者自带的配置），
    此时平台不接管、不做任何改动。
    """
    try:
        text = SETTINGS_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    states: list[bool] = []
    for name in _GENERAL_ENGINES:
        match = re.search(rf"^  - name: {re.escape(name)}\n    disabled: (true|false)$", text, re.M)
        if match:
            states.append(match.group(1) == "false")
    if not states:
        return None
    return all(states)


def apply_general_engines(enabled: bool) -> bool:
    """把「通用引擎」开关（Google/Bing/DuckDuckGo/Brave）落到 SearXNG 配置。

    只在平台自己生成的那份 settings.yml 上生效：文件里没有这批引擎条目（部署者自带配置）
    时直接跳过，不碰别人的文件。已是目标状态则**不重启容器**（幂等）；需要变更时按平台
    模板重写（保留原 ``secret_key``）并 ``docker restart searxng``。

    **永不自阻断**：任何一步失败只记日志并返回 False。
    """
    current = _current_general_engines_enabled()
    if current is None:
        logger.info("searxng provision: 未找到平台托管的 settings.yml，跳过通用引擎开关")
        return False
    if current is enabled:
        return True

    secret = _existing_secret() or secrets.token_urlsafe(32)
    try:
        SETTINGS_PATH.write_text(
            _settings_text(secret, general_engines=enabled), encoding="utf-8"
        )
    except OSError:
        logger.warning("searxng provision: 写入 %s 失败", SETTINGS_PATH, exc_info=True)
        return False

    if not _container_exists():
        logger.info("searxng provision: 容器不存在，配置已更新（下次创建时生效）")
        return True
    result = _run(["docker", "restart", CONTAINER_NAME], timeout=120)
    if not result or result.returncode != 0:
        logger.warning("searxng provision: 重启 %s 失败", CONTAINER_NAME)
        return False
    logger.info("searxng provision: 通用引擎开关已生效（general_engines=%s），容器已重启", enabled)
    return True


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


def _run_container(base_url: str, bind_addr: str, *, general_engines: bool) -> bool:
    _write_settings(general_engines=general_engines)
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
    general_engines: bool = False,
    attempts: int = 1,
) -> bool:
    """确保本机 SearXNG 可达；返回是否最终可用。**永不自阻断**。

    ``enabled=False``（控制台开关关掉）或环境变量
    ``RAVENHOLT_SEARXNG_AUTOPROVISION=0`` 时直接跳过，只做可达性判定不做容器操作。

    ``bind_addr`` 是新建容器时端口发布到的宿主地址（见 ``searxng_bind_addr`` 配置）：
    只做可达性判定；容器已存在时不动它的绑定，需要换绑请先 ``docker rm -f searxng``。

    ``general_engines`` 只在**新建容器**时生效（决定初始 settings.yml 里 Google/Bing/
    DuckDuckGo/Brave 是否启用）；已存在的容器请走 :func:`apply_general_engines`。
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
    elif not _run_container(url, bind_addr, general_engines=general_engines):
        return False

    # 容器刚起需要几秒初始化
    for _ in range(10):
        if _reachable(url):
            logger.info("searxng provision: 自动拉起成功（%s）", url)
            return True
        subprocess.run(["sleep", "2"], check=False)  # noqa: S603,S607 - 仅等待容器就绪
    logger.warning("searxng provision: 自动拉起后仍不可达（%s）", url)
    return False


__all__ = ["apply_general_engines", "ensure_local_searxng", "SETTINGS_PATH", "CONTAINER_NAME"]

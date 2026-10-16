import subprocess

import uvicorn

from app import create_app
from config import (
    WORKSPACE,
    get_config,
    load_config,
    reset_strix_settings_cache,
    sync_strix_image_env,
    sync_strix_llm_env,
    sync_strix_sandbox_env,
    sync_strix_search_env,
)
from logger import get_logger, setup_logging

logger = get_logger(__name__)


def _sync_sandbox_network() -> None:
    """注入沙箱网络前先确认该 docker 网络确实存在。

    配置了 ``sandbox.network`` 但网络缺失时（宿主换网段后未重建、或宿主 / 云不支持
    macvlan），不注入配置 —— 否则所有沙箱容器都会因网络不存在而创建失败。此时回退
    默认 bridge 网络，OOB 外带仍可走容器内预装的 interactsh。
    """
    name = get_config().sandbox.network.strip()
    if not name:
        return

    try:
        probe = subprocess.run(
            ["docker", "network", "inspect", name],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:  # noqa: BLE001 - docker 不可用时按网络缺失处理，回退 bridge
        logger.warning("校验沙箱网络 %s 失败，回退默认 bridge 网络", name, exc_info=True)
        return

    if probe.returncode != 0:
        logger.warning("沙箱网络 %s 不存在，回退默认 bridge 网络", name)
        return

    sync_strix_sandbox_env()


def _ensure_searxng_endpoint() -> None:
    """本机 SearXNG 不可达时尝试自动拉起容器（best-effort，失败不阻断启动）。

    零配置联网检索的保障：部署者不需要维护 SearXNG 容器的生命周期。
    检索侧还有无 key 安全数据库兜底，所以这里失败也不影响 agent 干活。
    """
    try:
        from core.searxng_provision import ensure_local_searxng

        integrations = get_config().integrations
        ensure_local_searxng(
            integrations.searxng_base_url,
            enabled=integrations.searxng_auto_provision,
            bind_addr=integrations.searxng_bind_addr,
        )
    except Exception:  # noqa: BLE001 - 自动保障绝不阻断启动
        logger.warning("SearXNG 自动保障异常（不影响启动）", exc_info=True)


def main() -> None:
    cfg = get_config()
    application = create_app()
    uvicorn.run(
        application,
        host=cfg.system.listen_addr,
        port=cfg.system.listen_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    load_config()
    setup_logging(level="INFO", file_path=WORKSPACE / "app.log")
    # 把 ravenholt 的模型配置同步给 strix 的内部调用（去重 / 压缩等）；
    # 必须在 create_app() 触发首次 strix load_settings() 之前执行。
    sync_strix_llm_env()
    # 把联网检索的 provider 与密钥同步给 strix（否则 web_search 恒返回「未配置」）。
    sync_strix_search_env()
    # strix 的 load_settings 是备忘化的：显式失效缓存，确保首次解析发生在本轮注入**之后**，
    # 避免任何早于这里的调用把 provider 固定成旧值。
    reset_strix_settings_cache()
    # 把会话沙箱镜像同步给 strix（用哪个镜像与网络是否可用无关，故独立于下一步）。
    sync_strix_image_env()
    # 把沙箱网络同步给 strix（先校验网络确实存在，缺失则回退 bridge）。
    _sync_sandbox_network()
    # 本机 SearXNG 不可达时自动拉起（零配置联网检索的保障；失败不影响启动）。
    _ensure_searxng_endpoint()

    main()

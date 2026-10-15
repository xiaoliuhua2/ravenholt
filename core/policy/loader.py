"""红线策略加载器：**fail-closed**。

文件缺失 / YAML 解析失败 / 校验失败 → 一律抛 :class:`PolicyError`；
调用方（应用启动流程）必须让它冒泡并拒绝启动，绝不允许「拿不到策略就裸跑」。
Tier-1 节被写成关闭状态时，pydantic 校验期就会失败。
"""

from __future__ import annotations

import threading
from pathlib import Path

import yaml
from pydantic import ValidationError

from config import WORKSPACE
from logger import get_logger
from schema.policy.policy import PolicyConfig


logger = get_logger(__name__)

POLICY_FILE = WORKSPACE / "policy.yaml"


class PolicyError(RuntimeError):
    """红线策略不可用（fail-closed）。"""


_lock = threading.RLock()
_policy: PolicyConfig | None = None
_policy_path: Path = POLICY_FILE


def load_policy(path: Path | None = None) -> PolicyConfig:
    """加载并校验策略；任何问题都以异常暴露，不返回默认值。"""
    global _policy, _policy_path

    target = path or _policy_path
    with _lock:
        try:
            raw = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyError(f"红线策略文件不可读：{target}（{exc}）") from exc

        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise PolicyError(f"红线策略 YAML 解析失败：{target}（{exc}）") from exc

        if not isinstance(data, dict):
            raise PolicyError(f"红线策略根节点必须是映射：{target}")

        try:
            policy = PolicyConfig.model_validate(data)
        except ValidationError as exc:
            raise PolicyError(f"红线策略校验失败：{target}\n{exc}") from exc

        _policy, _policy_path = policy, target
        logger.info("红线策略已加载：%s（revision=%s）", target, policy.revision)
        return policy


def get_policy() -> PolicyConfig:
    """取当前生效策略；未加载时抛错（不返回隐式默认值）。"""
    if _policy is None:
        raise PolicyError("红线策略尚未加载")
    return _policy


def policy_loaded() -> bool:
    return _policy is not None


def policy_path() -> Path:
    return _policy_path


# 写回是整体重写，原有手工注释不保留；注解版始终以 policy.yaml.example 为准。
_GENERATED_HEADER = (
    "# 本文件由 ravenholt 策略控制台写回：手工注释不再保留，注解版见 policy.yaml.example。\n"
    "# Tier-1 安全网（rate_limit / sandbox / kill_switch / audit）不可关闭，只能调参。\n"
)


def write_policy(policy: PolicyConfig, path: Path | None = None) -> Path:
    """把策略整体原子写回文件。

    写失败抛 ``OSError``（调用方负责回滚）；本函数只保证「临时文件 + 原子替换」，
    不做校验——传入前请已用 ``PolicyConfig`` 校验过。
    """
    target = path or _policy_path
    with _lock:
        body = yaml.safe_dump(
            policy.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_text(_GENERATED_HEADER + body, encoding="utf-8")
        tmp.replace(target)
        logger.info("红线策略已写回：%s（revision=%s）", target, policy.revision)
    return target

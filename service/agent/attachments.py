"""把回合输入里的附件图片交给 strix 运行时（图 + 转写双通道）。

主线（strix）运行时只接受一个文本任务，所以图片走**两条通道一起**：

1. **保真通道**：原图写入容器 ``/workspace/attachments/<sha12>.<ext>``，任务里给出路径，
   由沙箱内的 agent 自己用 tesseract / zbarimg / PIL 等工具处理 —— 零信息损失。
2. **提示通道**：用当前配置的多模态模型做一次「逐字转写」，附在任务里，提高 agent
   主动去查看文件的概率。

提示通道是 **best-effort**：模型不可用（例如未配 api_key）时只记日志并跳过，回合照常继续；
保真通道失败才报错。两条通了以后，若模型确实支持视觉，也可直接把图喂给模型。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import Sequence

from openai import AsyncOpenAI

from config import get_config
from logger import get_logger
from schema.agent.events import AgentImageInputPart, AgentInputPart, AgentTextInputPart
from service.sandbox.files import create_container_directory, write_container_bytes


logger = get_logger(__name__)

# ravenholt Kali 沙箱镜像的默认工作目录是 /workspace
ATTACHMENT_DIR = "/workspace/attachments"

_EXT_BY_MEDIA_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_MAX_DESCRIPTION_CHARS = 4000
_DESCRIBE_TIMEOUT_SECONDS = 60
_DESCRIBE_MAX_TOKENS = 1500

_TRANSCRIBE_SYSTEM_PROMPT = (
    "你是图片转写器，服务于已获授权的安全测试。"
    "只逐字转写图中所有可见文字：报错信息、URL、请求与响应行、HTTP 头、参数、JSON、"
    "表格、按钮与标签文案。保持原始大小写与符号，不要解释、不要总结、不要省略、不要补全、"
    "不要美化格式。图中没有文字时，用一句话客观描述画面内容，不要猜测用途或背景。"
)


def image_parts(content: Sequence[AgentInputPart] | None) -> list[AgentImageInputPart]:
    return [part for part in (content or []) if isinstance(part, AgentImageInputPart)]


def text_of(content: Sequence[AgentInputPart] | None) -> str:
    return "\n\n".join(
        part.text for part in (content or []) if isinstance(part, AgentTextInputPart)
    ).strip()


def _decode_image(part: AgentImageInputPart) -> bytes:
    return base64.b64decode("".join(part.data.split()))


def _attachment_target(part: AgentImageInputPart) -> tuple[str, bytes]:
    raw = _decode_image(part)
    digest = hashlib.sha256(raw).hexdigest()[:12]
    ext = _EXT_BY_MEDIA_TYPE.get(str(part.media_type), "bin")
    return f"{ATTACHMENT_DIR}/{digest}.{ext}", raw


async def persist_attachment_images(
    container_id: int, images: Sequence[AgentImageInputPart]
) -> list[str]:
    """把原图写进沙箱，返回容器内路径（同一张图内容相同 → 同名，重复上传无害）。"""
    if not images:
        return []
    await create_container_directory(container_id, ATTACHMENT_DIR)
    paths: list[str] = []
    for image in images:
        path, raw = _attachment_target(image)
        await write_container_bytes(container_id, path, raw)
        paths.append(path)
    return paths


async def describe_images(agent_code: str, images: Sequence[AgentImageInputPart]) -> str:
    """逐字转写（best-effort）：任何失败都返回空串，绝不阻塞回合。"""
    if not images:
        return ""
    cfg = get_config().agents.get(agent_code)
    if cfg is None:
        logger.warning("附件转写跳过：智能体 %s 未配置", agent_code)
        return ""

    user_content: list[dict] = [
        {"type": "text", "text": f"逐字转写以下 {len(images)} 张图片。"},
    ]
    for image in images:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image.media_type};base64,{image.data}"},
        })
    messages = [
        {"role": "system", "content": _TRANSCRIBE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    client = AsyncOpenAI(
        api_key=cfg.api_key or ("unused" if cfg.base_url else None),
        base_url=cfg.base_url or None,
        max_retries=1,
    )
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=cfg.model,
                messages=messages,
                max_tokens=_DESCRIBE_MAX_TOKENS,
                temperature=0,
            ),
            timeout=_DESCRIBE_TIMEOUT_SECONDS,
        )
        text = (response.choices[0].message.content or "").strip()
        return text[:_MAX_DESCRIPTION_CHARS]
    except Exception:  # noqa: BLE001 - 转写失败只降级，不影响回合
        logger.exception("附件转写失败（已跳过，仅保留沙箱原图通道）agent=%s", agent_code)
        return ""
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            logger.debug("closing attachment client failed", exc_info=True)


async def compose_strix_task(
    *,
    task: str,
    content: Sequence[AgentInputPart] | None,
    container_id: int | None,
    agent_code: str,
) -> str:
    """把富文本输入合成为运行时任务的最终文本（无图片时就是纯文本）。"""
    images = image_parts(content)
    base_text = (task or "").strip() or text_of(content)
    if not images:
        return base_text

    if container_id is None:
        # 没有沙箱容器就没有保真通道，只有一句有损转写 —— 宁可明确拒绝，也不要悄悄降级。
        raise ValueError("附件图片需要先为一个会话绑定沙箱容器，当前会话未绑定")

    paths = await persist_attachment_images(container_id, images)
    blocks: list[str] = []
    if base_text:
        blocks.append(base_text)
    blocks.append(
        "【附件】以下图片已**原样**放入沙箱，请自行查看"
        "（可用 tesseract 转文字、zbarimg 解二维码、python3 -c 配合 PIL 取像素/EXIF）：\n"
        + "\n".join(f"- {path}" for path in paths)
    )
    description = await describe_images(agent_code, images)
    if description:
        blocks.append(
            "【附件逐字转写（模型生成，可能有误，仅供参考；以沙箱内原图为准）】\n" + description
        )
    return "\n\n".join(blocks)


__all__ = [
    "ATTACHMENT_DIR",
    "compose_strix_task",
    "describe_images",
    "image_parts",
    "persist_attachment_images",
    "text_of",
]

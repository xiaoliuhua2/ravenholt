import { Button, TextArea, Toast } from "@douyinfe/semi-ui";
import { AtSign, ImagePlus, OctagonX, Pause, Send, X } from "lucide-react";
import { ClipboardEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentPicker } from "./AgentPicker";
import { PolicyGateControl } from "./PolicyGateControl";
import type { AgentImageInputPart, AgentInfo, AgentInputPart } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";

type ComposerProps = {
  streaming: boolean;
  disabled?: boolean;
  agents: AgentInfo[];
  activeAgentCode: string;
  agentSwitchDisabled?: boolean;
  canCancelAll?: boolean;
  onPickAgent: (code: string) => void;
  onSend: (content: AgentInputPart[]) => Promise<boolean>;
  onInterrupt: () => void;
  onCancelAll: () => void;
};

const ACCEPTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 3.75 * 1024 * 1024;
const MAX_TOTAL_IMAGE_BYTES = 6 * 1024 * 1024;

export function Composer({
  streaming,
  disabled = false,
  agents,
  activeAgentCode,
  agentSwitchDisabled = false,
  canCancelAll = false,
  onPickAgent,
  onSend,
  onInterrupt,
  onCancelAll,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<AgentImageInputPart[]>([]);
  const [highlight, setHighlight] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeAgent = useMemo(
    () => agents.find((agent) => agent.code === activeAgentCode) ?? null,
    [agents, activeAgentCode],
  );

  useEffect(() => {
    if (!pickerOpen) return;
    if (highlight >= agents.length) {
      setHighlight(Math.max(0, agents.length - 1));
    }
  }, [agents.length, highlight, pickerOpen]);

  const closePicker = useCallback(() => {
    setPickerOpen(false);
    setHighlight(0);
  }, []);

  useEffect(() => {
    if (!pickerOpen) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && wrapperRef.current?.contains(target)) return;
      closePicker();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [closePicker, pickerOpen]);

  const focusTextarea = useCallback(() => {
    wrapperRef.current?.querySelector("textarea")?.focus();
  }, []);

  const submit = async () => {
    const trimmed = text.trim();
    if ((!trimmed && images.length === 0) || streaming || disabled) return;
    const content: AgentInputPart[] = [
      ...(trimmed ? [{ type: "text" as const, text: trimmed }] : []),
      ...images,
    ];
    const sent = await onSend(content);
    if (!sent) return;
    setText("");
    setImages([]);
    closePicker();
  };

  const addImageFiles = useCallback(async (files: File[]) => {
    const imageFiles = files.filter((file) => ACCEPTED_IMAGE_TYPES.has(file.type));
    if (!imageFiles.length) return;
    const available = Math.max(0, MAX_IMAGES - images.length);
    if (available === 0) {
      Toast.warning(`At most ${MAX_IMAGES} images allowed`);
      return;
    }
    const next: AgentImageInputPart[] = [];
    const currentBytes = images.reduce((total, image) => total + base64DecodedSize(image.data), 0);
    let nextBytes = 0;
    for (const file of imageFiles.slice(0, available)) {
      if (file.size > MAX_IMAGE_BYTES) {
        Toast.warning(`${file.name} exceeds 3.75 MB, skipped`);
        continue;
      }
      if (currentBytes + nextBytes + file.size > MAX_TOTAL_IMAGE_BYTES) {
        Toast.warning("Total image size exceeds 6 MB, some images skipped");
        continue;
      }
      try {
        next.push(await fileToImagePart(file));
        nextBytes += file.size;
      } catch {
        Toast.error(`Failed to read ${file.name}`);
      }
    }
    if (next.length) {
      setImages((current) => [...current, ...next].slice(0, MAX_IMAGES));
    }
  }, [images]);

  const handlePaste = useCallback((event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files).filter((file) => ACCEPTED_IMAGE_TYPES.has(file.type));
    if (!files.length) return;
    event.preventDefault();
    void addImageFiles(files);
  }, [addImageFiles]);

  const pickAgent = (agent: AgentInfo) => {
    if (agentSwitchDisabled) return;
    onPickAgent(agent.code);
    closePicker();
    focusTextarea();
  };

  const toggleChip = () => {
    if (agentSwitchDisabled) return;
    setPickerOpen((next) => !next);
    focusTextarea();
  };

  const agentSwitchDisabledReason = "请先结束或取消正在运行的子智能体任务，再切换智能体";

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (pickerOpen) {
      if (event.key === "Escape") {
        event.preventDefault();
        closePicker();
        return;
      }
      if (event.key === "ArrowDown" && agents.length > 0) {
        event.preventDefault();
        setHighlight((index) => (index + 1) % agents.length);
        return;
      }
      if (event.key === "ArrowUp" && agents.length > 0) {
        event.preventDefault();
        setHighlight((index) => (index - 1 + agents.length) % agents.length);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (agents.length > 0 && !agentSwitchDisabled) pickAgent(agents[highlight]);
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        if (agents.length > 0 && !agentSwitchDisabled) pickAgent(agents[highlight]);
        return;
      }
    }

    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    if (streaming) {
      onInterrupt();
    } else {
      void submit();
    }
  };

  const action = streaming
    ? { icon: <Pause size={16} />, type: "danger" as const, title: "暂停", onClick: onInterrupt, disabled: false }
    : {
        icon: <Send size={16} />,
        type: "primary" as const,
        title: "发送",
        onClick: () => void submit(),
        disabled: disabled || (!text.trim() && images.length === 0),
      };

  return (
    <div ref={wrapperRef} className={cx("composer", streaming && "composer-streaming")}>
      <div className="composer-input">
        {pickerOpen && agents.length > 1 ? (
          <div className="composer-picker">
            <AgentPicker
              agents={agents}
              highlightedIndex={highlight}
              disabled={agentSwitchDisabled}
              disabledReason={agentSwitchDisabledReason}
              onHover={setHighlight}
              onSelect={pickAgent}
            />
          </div>
        ) : null}
        <div className="composer-panel">
          {images.length ? (
            <div className="composer-attachments">
              {images.map((image, index) => (
                <div key={`${image.media_type}:${index}:${image.data.length}`} className="composer-attachment">
                  <img src={`data:${image.media_type};base64,${image.data}`} alt="附件预览" />
                  <button
                    type="button"
                    className="composer-attachment-remove"
                    onClick={() => setImages((current) => current.filter((_, i) => i !== index))}
                    aria-label="移除图片"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <TextArea
            value={text}
            onChange={setText}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            autosize={{ minRows: 1, maxRows: 8 }}
            borderless
            disabled={disabled && !streaming}
            placeholder={
              disabled
                ? "正在加载会话历史…"
                : streaming
                  ? "正在流式输出… 按 Enter 或点击暂停可中断"
                  : "发送消息 · Shift+Enter 换行"
            }
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            className="composer-file-input"
            onChange={(event) => {
              const files = Array.from(event.currentTarget.files ?? []);
              event.currentTarget.value = "";
              void addImageFiles(files);
            }}
          />
          <div className="composer-footer">
            {/* 只有一套模型预设时没有可切换的对象，隐藏切换入口 */}
            {agents.length > 1 ? (
              <button
                type="button"
                className="composer-agent-chip"
                onClick={toggleChip}
                disabled={agentSwitchDisabled}
                aria-label={activeAgent ? `与 ${activeAgent.name} 对话` : "选择智能体"}
                title={agentSwitchDisabled ? agentSwitchDisabledReason : activeAgent ? "点击切换智能体" : "选择智能体"}
              >
                <AtSign size={14} />
                <span>{activeAgent?.name || "智能体"}</span>
              </button>
            ) : null}
            <div className="composer-actions">
              <PolicyGateControl onOpen={closePicker} />
              <Button
                className="composer-action-button"
                icon={<ImagePlus size={16} />}
                theme="borderless"
                type="tertiary"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || streaming || images.length >= MAX_IMAGES}
                aria-label="附加图片"
                title="附加图片"
              />
              <Button
                className="composer-action-button"
                icon={action.icon}
                theme="solid"
                type={action.type}
                onClick={action.onClick}
                disabled={action.disabled}
                aria-label={streaming ? "中断输出" : "发送消息"}
                title={action.title}
              />
              <Button
                className="composer-action-button"
                icon={<OctagonX size={16} />}
                theme="borderless"
                type="danger"
                onClick={onCancelAll}
                disabled={disabled || !canCancelAll}
                aria-label="取消所有运行中的子智能体任务"
                title={canCancelAll ? "取消所有运行中的子智能体任务" : "没有运行中的子智能体任务"}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function base64DecodedSize(value: string): number {
  const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor(value.length * 3 / 4) - padding);
}

function fileToImagePart(file: File): Promise<AgentImageInputPart> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      const [prefix, data] = value.split(",", 2);
      const match = /^data:(image\/(?:png|jpeg|webp));base64$/.exec(prefix);
      if (!match || !data) {
        reject(new Error("invalid image data"));
        return;
      }
      resolve({
        type: "image",
        media_type: match[1] as AgentImageInputPart["media_type"],
        data,
        detail: "auto",
      });
    };
    reader.onerror = () => reject(reader.error ?? new Error("failed to read image"));
    reader.readAsDataURL(file);
  });
}

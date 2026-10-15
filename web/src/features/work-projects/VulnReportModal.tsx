import { useEffect, useState } from "react";
import { MarkdownRenderer } from "../playground/MarkdownRenderer";
import type { WorkProjectFinding, WorkProjectFindingEvidence } from "../../shared/api/types";
import { getWorkProjectFindingEvidence } from "../../shared/api/workProjects";
import { WORK_PROJECT_FINDING_SEVERITY_LABEL } from "../../shared/lib/labels";

/**
 * 把「项目发现」渲染成 src-hunt 规范版漏洞报告（7 段结构）。
 * 格式唯一来源：src-hunt/references/03-vuln-report-format.md
 *   # 安全漏洞报告
 *   ## 一、漏洞基本信息（表格：漏洞标题/目标系统/目标URL/漏洞类型/漏洞等级/危害面/测试账号）
 *   ## 二、漏洞概述
 *   ## 三、影响与危害
 *   ## 四、涉及接口清单（表格：序号/接口/说明/来源）
 *   ## 五、复现过程（环境信息 + 步骤，整包放 ```http 围栏）
 *   ## 六、漏洞成因分析
 *   ## 七、修复建议
 *   大段之间用 `---` 分隔。
 *
 * 复现过程优先用平台落库的**可重放证据包**（evidence 表：完整请求 + baseline/probe 响应）；
 * 没有关联证据时才退回 finding.description 的扁平字段文本。
 */

const FLAT_LABELS = [
  "来源",
  "报告代理",
  "目标",
  "接口",
  "CVE",
  "CWE",
  "描述",
  "技术分析",
  "验证方法",
  "复现说明",
  "证据",
  "修复建议",
] as const;
type FlatLabel = (typeof FLAT_LABELS)[number];

// 容忍 agent 的多种写法：`目标：x` / `### 来源: x` / `- **CVE：** x`
const LABEL_PATTERN = new RegExp(
  `^\\s*(?:[-*]\\s*)?(?:#{1,6}\\s*)?(?:\\*\\*)?(${FLAT_LABELS.join("|")})(?:\\*\\*)?\\s*[:：]\\s*(.*)$`,
);

const SPEC_HEADING = /(^|\n)#{1,6}\s*一、/;

// src-hunt 规范「整包」一条要求写齐的公共头（值为规范给定的固定模板）。
const SPEC_COMMON_HEADERS: Array<[string, string]> = [
  ["Accept", "*/*"],
  ["Accept-Language", "zh-CN"],
  ["Accept-Encoding", "gzip, deflate"],
  [
    "User-Agent",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 10.0; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Tablet PC 2.0)",
  ],
  ["Connection", "close"],
];

const STATUS_REASON: Record<number, string> = {
  200: "OK",
  201: "Created",
  204: "No Content",
  301: "Moved Permanently",
  302: "Found",
  303: "See Other",
  307: "Temporary Redirect",
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  405: "Method Not Allowed",
  415: "Unsupported Media Type",
  429: "Too Many Requests",
  500: "Internal Server Error",
  502: "Bad Gateway",
  503: "Service Unavailable",
};

const VERDICT_LABEL: Record<string, string> = {
  reproduced: "已复现（独立重放后 baseline 与 probe 仍存在差分）",
  refuted: "未复现（独立重放后与 baseline 等价）",
  error: "重放失败（验证器无法完成重放）",
};

const MAX_BODY_CHARS = 20000;

function parseFlatReport(description: string): Map<FlatLabel, string> {
  const sections = new Map<FlatLabel, string>();
  let current: FlatLabel | null = null;
  let buffer: string[] = [];
  const flush = () => {
    if (current) sections.set(current, buffer.join("\n").trim());
  };
  for (const line of description.split(/\r?\n/)) {
    const matched = line.match(LABEL_PATTERN);
    if (matched) {
      flush();
      current = matched[1] as FlatLabel;
      buffer = matched[2] ? [matched[2]] : [];
    } else if (current) {
      buffer.push(line);
    }
  }
  flush();
  return sections;
}

function firstSentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  const cut = trimmed.search(/[。！？\n]/);
  return cut === -1 ? trimmed : trimmed.slice(0, cut + 1);
}

function section(title: string, body: string[]): string[] {
  const content = body.map((part) => part.trim()).filter(Boolean).join("\n\n");
  return [`## ${title}`, "", content || "*（本次发现未提供该段内容）*", "", "---", ""];
}

function cell(value: string | undefined): string {
  return (value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim() || "—";
}

function httpBlock(text: string): string {
  return `\`\`\`http\n${text.replace(/\n+$/, "")}\n\`\`\``;
}

function splitUrl(url: string): { host: string; path: string } {
  try {
    const parsed = new URL(url);
    return {
      host: parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname,
      path: `${parsed.pathname}${parsed.search}` || "/",
    };
  } catch {
    return { host: url.replace(/^https?:\/\//, "").split("/")[0] || "—", path: "/" };
  }
}

function bodyBytes(body: string): number {
  return new TextEncoder().encode(body).length;
}

/** 完整请求包：请求行 + Host + 规范公共头 + 证据里的真实头 + body 相关头。 */
export function buildRequestPackage(evidence: WorkProjectFindingEvidence): string {
  const { host, path } = splitUrl(evidence.url);
  const heads = new Map<string, { name: string; value: string }>();
  const put = (name: string, value: string) => heads.set(name.toLowerCase(), { name, value });
  put("Host", host);
  for (const [name, value] of SPEC_COMMON_HEADERS) put(name, value);
  // 证据里的真实头覆盖同名公共头（例如 Cookie 必须写完整实值）。
  for (const [name, value] of Object.entries(evidence.request_headers ?? {})) put(name, String(value));

  const body = evidence.request_body ?? "";
  if (body) {
    if (!heads.has("content-type")) put("Content-Type", "application/x-www-form-urlencoded");
    put("Content-Length", String(bodyBytes(body)));
    put("Cache-Control", "no-cache");
  }

  const lines = [
    `${(evidence.method || "GET").toUpperCase()} ${path} HTTP/1.1`,
    ...[...heads.values()].map((head) => `${head.name}: ${head.value}`),
    "",
    body,
  ];
  return lines.join("\n");
}

function statusLine(status: number): string {
  const reason = STATUS_REASON[status] ?? "";
  return `HTTP/1.1 ${status || "—"}${reason ? ` ${reason}` : ""}`;
}

function snippet(text: string, limit = 120): string {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  if (!flat) return "";
  return flat.length > limit ? `${flat.slice(0, limit)}……` : flat;
}

/**
 * src-hunt 规范《整包（步骤里）》原文要求「步骤里只贴请求包、不贴回包」，
 * 故响应只作「状态码 + 正文一句话」概括，不贴 ```http 响应块。
 */
function responseSummary(evidence: WorkProjectFindingEvidence): string {
  const probeBody = snippet(evidence.probe_body);
  const probe = probeBody
    ? `探测响应：${statusLine(evidence.probe_status)}，正文：${probeBody}`
    : `探测响应：${statusLine(
        evidence.probe_status,
      )}，正文为空 —— 该次验证的差分不在 HTTP 响应体（走带外通道或时序），判定以带外记录为准`;

  const sameAsProbe =
    evidence.baseline_status === evidence.probe_status &&
    (evidence.baseline_body ?? "") === (evidence.probe_body ?? "");
  const baselineBody = snippet(evidence.baseline_body);
  const baseline = sameAsProbe
    ? `对照响应：${statusLine(evidence.baseline_status)}，与探测响应同形`
    : baselineBody
      ? `对照响应：${statusLine(evidence.baseline_status)}，正文：${baselineBody}`
      : `对照响应：${statusLine(evidence.baseline_status)}，正文为空`;

  return ["**响应**", "", `- ${probe}`, `- ${baseline}`].join("\n");
}

/** 证据包渲染块：环境信息 + 步骤一 + 完整请求包 + 响应一句话概括（两条渲染路径共用）。 */
function evidenceBlocks(evidence: WorkProjectFindingEvidence): string[] {
  const { host, path } = splitUrl(evidence.url);
  const envLines = [
    `- 目标系统：${evidence.target || host || "—"}`,
    `- 目标地址：${evidence.url || "—"}`,
    `- 验证时间：${evidence.captured_at || "—"}`,
    `- 独立验证：${VERDICT_LABEL[evidence.verdict] ?? (evidence.verdict || "尚未重放")}${
      evidence.verifier_note ? `（${evidence.verifier_note}）` : ""
    }`,
  ];
  return [
    ["**环境信息**", "", ...envLines].join("\n"),
    `**步骤一：${(evidence.method || "GET").toUpperCase()} ${path}**`,
    "请求包（完整可重放，直接粘进重放器即可）：",
    httpBlock(buildRequestPackage(evidence)),
    responseSummary(evidence),
  ];
}

/** 落库正文已是规范 7 段时：骨架原样保留，只把平台可重放证据注入「五、复现过程」段末。 */
function injectEvidenceIntoSpec(spec: string, evidence: WorkProjectFindingEvidence): string {
  const marker = "## 五、复现过程";
  const start = spec.indexOf(marker);
  if (start === -1) return spec;
  const nextHeading = spec.indexOf("\n## ", start + marker.length);
  const segEnd = nextHeading === -1 ? spec.length : nextHeading;
  const hrIdx = spec.slice(start, segEnd).lastIndexOf("\n---");
  const insertAt = hrIdx === -1 ? segEnd : start + hrIdx;
  const block = ["", "**平台重放证据（可复制的完整请求包）**", "", ...evidenceBlocks(evidence), ""].join("\n");
  return spec.slice(0, insertAt) + block + spec.slice(insertAt);
}

function reproduceSection(
  flat: Map<FlatLabel, string>,
  evidence: WorkProjectFindingEvidence | null,
): string[] {
  if (!evidence) {
    // 无关联证据：退回 agent 自述文本（如实，不可重放）。
    const fallback = [flat.get("验证方法"), flat.get("复现说明"), flat.get("证据")].filter(
      (part): part is string => Boolean(part?.trim()),
    );
    return section("五、复现过程", [
      "*（本条发现未关联可重放证据包，以下为 agent 自述，尚未经平台重放验证）*",
      ...fallback,
    ]);
  }

  const body: string[] = [];
  const narrative = [flat.get("验证方法"), flat.get("复现说明")].filter(
    (part): part is string => Boolean(part?.trim()),
  );
  if (narrative.length) body.push(narrative.join("\n\n"));
  body.push(...evidenceBlocks(evidence));

  return section("五、复现过程", body);
}

export function buildVulnReportMarkdown(
  finding: WorkProjectFinding,
  evidence?: WorkProjectFindingEvidence | null,
): string {
  const description = (finding.description ?? "").trim();
  if (SPEC_HEADING.test(description)) {
    // 落库正文已是规范 7 段（agent 提交即按 src-hunt 骨架写）⇒ 骨架原样渲染，
    // 仅把证据包注入「五、复现过程」，保证可重放整包不丢。
    return evidence ? injectEvidenceIntoSpec(description, evidence) : description;
  }

  const flat = parseFlatReport(description);
  const targetUrl = evidence?.url || flat.get("目标");
  const severity = WORK_PROJECT_FINDING_SEVERITY_LABEL[finding.severity] ?? "—";
  const looksAnonymous = /未认证|匿名|未登录/.test(`${finding.title} ${description}`);
  const typeParts = [flat.get("CVE"), flat.get("CWE")].filter(Boolean).join(" / ");
  const overview = flat.get("描述") ?? description;

  const lines: string[] = [
    "# 安全漏洞报告",
    "",
    "## 一、漏洞基本信息",
    "",
    "| 项 | 内容 |",
    "| --- | --- |",
    `| 漏洞标题 | ${cell(finding.title)} |`,
    `| 目标系统 | ${cell(evidence?.target ?? flat.get("目标"))} |`,
    `| 目标 URL | ${cell(targetUrl)} |`,
    `| 漏洞类型 | ${cell(typeParts)} |`,
    `| 漏洞等级 | ${cell(severity)} |`,
    `| 危害面 | ${cell(firstSentence(finding.impact ?? ""))} |`,
    `| 测试账号 | ${looksAnonymous ? "未登录（匿名）" : "—"} |`,
    "",
    "---",
    "",
    ...section("二、漏洞概述", [overview]),
    ...section("三、影响与危害", [finding.impact ?? ""]),
    ...section("四、涉及接口清单", [
      [
        "| 序号 | 接口 | 说明 | 来源 |",
        "| --- | --- | --- | --- |",
        `| 1 | ${cell(evidence ? `${evidence.method} ${evidence.url}` : flat.get("接口"))} | ${cell(
          finding.title,
        )} | ${cell(flat.get("来源"))} |`,
      ].join("\n"),
    ]),
    ...reproduceSection(flat, evidence ?? null),
    ...section("六、漏洞成因分析", [flat.get("技术分析") ?? ""]),
    ...section("七、修复建议", [flat.get("修复建议") ?? ""]),
  ];
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + "\n";
}

type VulnReportModalProps = {
  open: boolean;
  finding: WorkProjectFinding | null;
  projectId?: number;
  onClose: () => void;
};

export function VulnReportModal({ open, finding, projectId, onClose }: VulnReportModalProps) {
  const [evidence, setEvidence] = useState<WorkProjectFindingEvidence | null>(null);
  const [evidenceError, setEvidenceError] = useState("");

  useEffect(() => {
    if (!open || !finding) return;
    if (!finding.evidence_id || !projectId) {
      setEvidence(null);
      setEvidenceError("");
      return;
    }
    let canceled = false;
    setEvidence(null);
    setEvidenceError("");
    fetchFindingEvidence(projectId, finding)
      .then((value) => {
        if (!canceled) setEvidence(value);
      })
      .catch(() => {
        if (!canceled) setEvidenceError("证据包加载失败");
      });
    return () => {
      canceled = true;
    };
  }, [open, finding, projectId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open || !finding) return null;
  return (
    <div className="vuln-report-overlay" role="presentation" onClick={onClose}>
      <section
        className="vuln-report-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`漏洞报告：${finding.title}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="vuln-report-head">
          <div className="vuln-report-head-text">
            <strong>{finding.title}</strong>
          </div>
          <button type="button" className="vuln-report-close" aria-label="关闭报告" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="vuln-report-body">
          {finding.evidence_id && !evidence && !evidenceError ? (
            <p className="vuln-report-hint">正在加载可重放证据包…</p>
          ) : null}
          {evidenceError ? <p className="vuln-report-hint">{evidenceError}</p> : null}
          <MarkdownRenderer markdown={buildVulnReportMarkdown(finding, evidence)} />
        </div>
      </section>
    </div>
  );
}

/** 拉取该发现关联的可重放证据包；未关联 / 无项目 id 时返回 null。 */
export async function fetchFindingEvidence(
  projectId: number | undefined,
  finding: WorkProjectFinding,
): Promise<WorkProjectFindingEvidence | null> {
  if (!projectId || !finding.evidence_id) return null;
  const res = await getWorkProjectFindingEvidence(projectId, finding.id);
  return res.data ?? null;
}

/** src-hunt 落盘规则：文件名就是漏洞标题那一行，后缀 `.md`；非法字符清洗掉。 */
function reportFileName(title: string): string {
  const safe = (title ?? "")
    // eslint-disable-next-line no-control-regex
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_")
    .replace(/\s+/g, " ")
    .trim();
  return `${safe || "vulnerability-report"}.md`;
}

export type ReportSaveResult = "saved" | "downloaded" | "canceled";

/**
 * 保存导出的 `.md`。
 * 优先用 File System Access API 让用户选保存位置；该 API 仅在安全上下文
 * （https 或 localhost）可用，http 源下自动回退为浏览器默认下载。
 * 换行按 src-hunt 落盘规则转 CRLF。
 */
export async function saveMarkdownFile(fileName: string, markdown: string): Promise<ReportSaveResult> {
  const payload = markdown.replace(/\r?\n/g, "\r\n");
  const blob = new Blob([payload], { type: "text/markdown;charset=utf-8" });
  const picker = (
    window as unknown as {
      showSaveFilePicker?: (options: {
        suggestedName: string;
        types: { description: string; accept: Record<string, string[]> }[];
      }) => Promise<FileSystemFileHandle>;
    }
  ).showSaveFilePicker;
  if (typeof picker === "function") {
    try {
      const handle = await picker({
        suggestedName: fileName,
        types: [{ description: "Markdown", accept: { "text/markdown": [".md"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return "saved";
    } catch (error) {
      if ((error as DOMException | undefined)?.name === "AbortError") return "canceled";
    }
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return "downloaded";
}

/** 发现卡片上的一行预览：规范正文取「二、漏洞概述」，并去掉 Markdown 记号。 */
export function reportPreviewText(description: string): string {
  const text = (description ?? "").trim();
  if (!/^#\s*安全漏洞报告/.test(text)) return text;
  const matched = text.match(/##\s*二、漏洞概述\s*\n+([\s\S]*?)(?:\n---|\n##\s|$)/);
  return (matched?.[1] ?? text)
    .split(/\r?\n/)
    .filter((line) => !line.trim().startsWith("|"))
    .join(" ")
    .replace(/[*`>#]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** 导出整份报告（与抽屉所见一致）为 `.md`，供发现卡片右下角的「导出」按钮调用。 */
export async function exportFindingReport(
  projectId: number | undefined,
  finding: WorkProjectFinding,
): Promise<ReportSaveResult> {
  let evidence: WorkProjectFindingEvidence | null = null;
  try {
    evidence = await fetchFindingEvidence(projectId, finding);
  } catch {
    evidence = null; // 取不到证据包时仍导出正文骨架
  }
  return saveMarkdownFile(reportFileName(finding.title), buildVulnReportMarkdown(finding, evidence));
}

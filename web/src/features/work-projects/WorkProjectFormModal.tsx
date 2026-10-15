import { Button, Input, InputNumber, Select, Spin, Tag, TextArea } from "@douyinfe/semi-ui";
import { FolderKanban, ScanSearch, Trash2, Upload, UserRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  WORK_PROJECT_ASSET_ORIGIN,
  getWorkProjectAssetTypes,
  getWorkProjectTypes,
  isWorkProjectAssetType,
  isWorkProjectType,
  WORK_PROJECT_ASSET_TYPE,
} from "../../shared/api/contract";
import { querySystemUsers } from "../../shared/api/systemUsers";
import { uploadWorkProjectSource } from "../../shared/api/workProjects";
import type {
  CreateWorkProjectRequest,
  SystemUser,
  WorkProject,
  WorkProjectAssetRequest,
} from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";
import { useOptionList } from "../../shared/hooks/useOptionList";
import {
  SYSTEM_USER_ROLE_COLOR,
  SYSTEM_USER_ROLE_LABEL,
  WORK_PROJECT_ASSET_TYPE_LABEL,
  WORK_PROJECT_TYPE_LABEL,
} from "../../shared/lib/labels";

type WorkProjectFormModalProps = {
  open: boolean;
  saving: boolean;
  project?: WorkProject | null;
  onCancel: () => void;
  onSubmit: (payload: CreateWorkProjectRequest) => Promise<void>;
};

type SelectedOption = {
  value?: SystemUser["id"];
};

type AssetFormRow = WorkProjectAssetRequest & {
  existingId?: number;
};

// 批量导入：每行的解析结果，用于内联标注「已导入 / 重复跳过 / 无法解析」。
type BulkLine = {
  raw: string;
  status: "ok" | "duplicate" | "error";
  message: string;
  asset?: WorkProjectAssetRequest;
};

type WorkProjectFormValues = Omit<CreateWorkProjectRequest, "assets" | "sandbox_container_ids"> & {
  assets: AssetFormRow[];
  // 表单内始终是数组：创建项目必须选沙箱，避免 undefined 参与必填校验。
  sandbox_container_ids: number[];
};

const projectTypes = getWorkProjectTypes();
const assetTypes = getWorkProjectAssetTypes();

// 批量导入的输入示例，同时充当格式说明。
const BULK_PLACEHOLDER = [
  "# 每行一个资产，# 开头的行忽略",
  "192.168.1.10:8080",
  "app.example.com",
  "10.0.0.0/24",
  "/opt/source",
].join("\n");

const BULK_STATUS_LABEL: Record<BulkLine["status"], string> = {
  ok: "已导入",
  duplicate: "重复跳过",
  error: "无法解析",
};

const EMPTY_ASSET: AssetFormRow = {
  type: assetTypes[0],
  path: "",
  host: "",
  port: null,
};

const EMPTY: WorkProjectFormValues = {
  name: "",
  description: "",
  owner_user_ids: [],
  sandbox_container_ids: [],
  assets: [{ ...EMPTY_ASSET }],
  type: projectTypes[0],
};

export function WorkProjectFormModal({ open, saving, project, onCancel, onSubmit }: WorkProjectFormModalProps) {
  const [values, setValues] = useState<WorkProjectFormValues>(EMPTY);
  const [bulkText, setBulkText] = useState("");
  const [bulkReport, setBulkReport] = useState<BulkLine[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState("");
  const [uploadError, setUploadError] = useState("");
  const sourceInputRef = useRef<HTMLInputElement>(null);
  const { items: users, loading: usersLoading } = useOptionList<SystemUser>({
    enabled: open,
    query: querySystemUsers,
  });
  const editing = Boolean(project);

  useEffect(() => {
    if (!open) return;
    setValues(project ? {
      name: project.name,
      description: project.description,
      owner_user_ids: project.owner_user_ids,
      sandbox_container_ids: project.sandbox_container_ids,
      assets: scopeAssetsFromProject(project),
      type: project.type,
    } : { ...EMPTY, assets: [{ ...EMPTY_ASSET }] });
    setBulkText("");
    setBulkReport([]);
    setUploadNote("");
    setUploadError("");
  }, [open, project]);

  const userOptionList = useMemo(() => users.map((user) => ({
    label: <UserOption user={user} />,
    value: user.id,
  })), [users]);
  // 沙箱由运行时按会话自动 provision，项目不再需要预先绑定容器。
  const canSubmit = Boolean(values.name.trim()) && values.assets.length > 0
    && values.assets.every(isAssetComplete);
  // 资产输入按类型分成「一个主入口」，不再有逐行编辑：
  // - 源码审计：上传源码包（没资产时资产区显示居中的投放入口）
  // - 渗透测试：批量导入（粘贴多行，自动识别类型）
  // 有资产之后才显示资产行（源码审计=二进制路径行，渗透=导入结果行）。
  const isSourceAudit = values.type === "source_code_audit";
  const hasAssets = values.assets.some((asset) => !isAssetEmpty(asset));

  const updateAsset = (index: number, patch: Partial<AssetFormRow>) => {
    setValues((current) => ({
      ...current,
      assets: current.assets.map((asset, assetIndex) => (
        assetIndex === index ? { ...asset, ...patch } : asset
      )),
    }));
  };

  const removeAsset = (index: number) => {
    setValues((current) => ({
      ...current,
      assets: current.assets.filter((_, assetIndex) => assetIndex !== index),
    }));
  };

  // 追加资产前清掉尚未填写的空白行（含默认占位行），否则这些空行会挡住提交校验；
  // 编辑模式下已有 id 的行始终保留。
  const appendAssets = (added: AssetFormRow[]) => {
    if (!added.length) return;
    setValues((current) => ({
      ...current,
      assets: [
        ...current.assets.filter((asset) => asset.existingId || !isAssetEmpty(asset)),
        ...added,
      ],
    }));
  };

  // 上传源码包：后端解压到服务器目录，返回的 server_path 直接成为一条 binary 资产。
  const uploadSourceArchive = async (file: File) => {
    setUploadError("");
    setUploadNote("");
    setUploading(true);
    try {
      const response = await uploadWorkProjectSource(file);
      const upload = response.data;
      if (!upload) {
        setUploadError(response.message || "上传失败");
        return;
      }
      appendAssets([{
        type: WORK_PROJECT_ASSET_TYPE.BINARY,
        host: "",
        port: null,
        path: upload.server_path,
      }]);
      setUploadNote(`已解压 ${upload.file_count} 个文件到 ${upload.server_path}`);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  // 解析粘贴的多行资产：有效的按 identity 去重后追加为可继续编辑的普通行，
  // 解析失败的行留在文本框里便于就地修正，并以内联标注说明原因。
  const runBulkImport = () => {
    const seen = new Set(values.assets.map(assetIdentity));
    const accepted: AssetFormRow[] = [];
    const report: BulkLine[] = [];
    const unparsed: string[] = [];
    for (const line of bulkText.split("\n")) {
      const raw = line.trim();
      if (!raw || raw.startsWith("#")) continue;
      const parsed = parseBulkLine(raw);
      if (!parsed.asset) {
        report.push({ raw, status: "error", message: parsed.error ?? "无法识别" });
        unparsed.push(raw);
        continue;
      }
      const identity = assetIdentity(parsed.asset);
      if (seen.has(identity)) {
        report.push({ raw, status: "duplicate", message: "与已有资产重复，已跳过", asset: parsed.asset });
        continue;
      }
      seen.add(identity);
      accepted.push(parsed.asset);
      report.push({ raw, status: "ok", message: "已追加到资产列表", asset: parsed.asset });
    }
    if (accepted.length) {
      appendAssets(accepted);
    }
    const hasIssues = report.some((item) => item.status !== "ok") || unparsed.length > 0;
    setBulkReport(report);
    setBulkText(unparsed.join("\n"));
    if (!hasIssues) {
      setBulkReport([]);
    }
  };

  const submit = () => onSubmit({
    ...values,
    name: values.name.trim(),
    description: values.description.trim(),
    assets: values.assets.map(normalizeAsset).filter(isAssetComplete),
  });

  return (
    <ResourceModal
      open={open}
      title={editing ? "编辑工作项目" : "创建工作项目"}
      saving={saving}
      submitLabel={editing ? "保存" : "创建"}
      submitDisabled={!canSubmit}
      width={980}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <div className="project-form-grid">
        <label>
          <span>名称</span>
          <Input prefix={<FolderKanban size={16} />} value={values.name} maxLength={255} required
            onChange={(name) => setValues((v) => ({ ...v, name }))}
          />
        </label>
        <label>
          <span>类型</span>
          <Select prefix={<ScanSearch size={16} />} value={values.type}
            onChange={(type) => isWorkProjectType(type) && setValues((v) => ({ ...v, type }))}
            optionList={projectTypes.map((type) => ({ label: WORK_PROJECT_TYPE_LABEL[type], value: type }))}
          />
        </label>
        <label>
          <span>负责人</span>
          <Select
            prefix={<UserRound size={16} />}
            value={values.owner_user_ids}
            optionList={userOptionList}
            placeholder={usersLoading ? "加载中…" : "选择项目负责人"}
            emptyContent={usersLoading ? <Spin size="small" /> : "暂无用户"}
            loading={usersLoading}
            multiple
            renderSelectedItem={(option: SelectedOption) => ({
              isRenderInTag: true,
              content: users.find((user) => user.id === option.value)?.username ?? String(option.value ?? ""),
            })}
            showClear
            onClear={() => setValues((v) => ({ ...v, owner_user_ids: [] }))}
            onChange={(value) => setValues((v) => ({
              ...v,
              owner_user_ids: Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [],
            }))}
          />
        </label>
      </div>

      <label>
        <span>描述</span>
        <TextArea value={values.description} maxLength={2000} autosize={{ minRows: 3, maxRows: 6 }}
          onChange={(description) => setValues((v) => ({ ...v, description }))}
        />
      </label>

      <section className="project-assets-editor">
        <header>
          <span>资产</span>
        </header>
        {isSourceAudit ? (
          <input
            ref={sourceInputRef}
            type="file"
            className="sr-only"
            aria-label="选择源码包"
            accept=".zip,.tar,.gz,.tgz,.tbz2,.xz"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void uploadSourceArchive(file);
            }}
          />
        ) : null}
        {uploadNote || uploadError ? (
          <p className="project-assets-note" data-status={uploadError ? "error" : "ok"}>
            {uploadError || uploadNote}
          </p>
        ) : null}
        {!isSourceAudit ? (
          <div className="project-assets-import">
            <label>
              <span>批量粘贴</span>
              <TextArea
                value={bulkText}
                autosize={{ minRows: 4, maxRows: 8 }}
                placeholder={BULK_PLACEHOLDER}
                onChange={setBulkText}
              />
            </label>
            <p className="project-assets-import-hint">
              每行一个资产，自动识别类型：<code>主机:端口</code> → 服务，IPv4 / CIDR → 网络，
              <code>/路径</code> → 二进制，其余 → 域名；<code>#</code> 开头的行忽略。
            </p>
            <div className="project-assets-import-actions">
              <Button
                size="small"
                theme="solid"
                type="primary"
                htmlType="button"
                disabled={!bulkText.trim()}
                onClick={runBulkImport}
              >
                解析并导入
              </Button>
              {bulkReport.length ? (
                <span className="project-assets-import-summary mono">{bulkSummary(bulkReport)}</span>
              ) : null}
            </div>
            {bulkReport.length ? (
              <ul className="project-assets-import-report">
                {bulkReport.map((item, index) => (
                  <li key={index} className="project-assets-import-line" data-status={item.status}>
                    <span className="project-assets-import-raw mono">{item.raw}</span>
                    <span className="project-assets-import-status">{BULK_STATUS_LABEL[item.status]}</span>
                    {item.asset ? (
                      <span className="mono">{WORK_PROJECT_ASSET_TYPE_LABEL[item.asset.type]}</span>
                    ) : null}
                    <small>{item.message}</small>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {hasAssets ? (
          <div className="project-assets-rows">
            {values.assets.map((asset, index) => (
              <article key={index} className="project-asset-row">
                <label>
                  <span>类型</span>
                  <Select
                    value={asset.type}
                    disabled={Boolean(asset.existingId)}
                    optionList={assetTypes.map((type) => ({ label: WORK_PROJECT_ASSET_TYPE_LABEL[type], value: type }))}
                    onChange={(type) => isWorkProjectAssetType(type) && updateAsset(index, resetAssetForType(type))}
                  />
                </label>
                {asset.type === WORK_PROJECT_ASSET_TYPE.BINARY ? (
                  <label>
                    <span>路径</span>
                    <Input
                      value={asset.path}
                      maxLength={500}
                      required
                      onChange={(path) => updateAsset(index, { path })}
                    />
                  </label>
                ) : (
                  <>
                    <label>
                      <span>{ASSET_HOST_FIELD_LABEL[asset.type]}</span>
                      <Input value={asset.host} maxLength={255} onChange={(host) => updateAsset(index, { host })} />
                    </label>
                    {asset.type === WORK_PROJECT_ASSET_TYPE.SERVICE ? (
                      <label>
                        <span>端口</span>
                        <InputNumber value={asset.port ?? undefined} min={1} max={65535} onChange={(port) => updateAsset(index, { port: typeof port === "number" ? port : null })} />
                      </label>
                    ) : null}
                  </>
                )}
                <Button
                  icon={<Trash2 size={14} />}
                  theme="borderless"
                  type="danger"
                  aria-label="移除资产"
                  onClick={() => removeAsset(index)}
                />
              </article>
            ))}
          </div>
        ) : isSourceAudit ? (
          <div className="project-assets-source">
            <Button
              icon={<Upload size={16} />}
              theme="borderless"
              type="tertiary"
              htmlType="button"
              loading={uploading}
              onClick={() => sourceInputRef.current?.click()}
            >
              上传源码包
            </Button>
            <p className="project-assets-source-hint">
              支持 .zip / .tar / .tar.gz；上传后自动解压成一条二进制资产，审计时会把源码挂进沙箱。
            </p>
          </div>
        ) : null}
      </section>
    </ResourceModal>
  );
}

function UserOption({ user }: { user: SystemUser }) {
  return (
    <div className="project-user-option">
      <span>{user.username}</span>
      <small>{user.email || "无邮箱"}</small>
      <Tag color={SYSTEM_USER_ROLE_COLOR[user.role]}>{SYSTEM_USER_ROLE_LABEL[user.role]}</Tag>
    </div>
  );
}

function assetFromProject(asset: WorkProject["assets"][number]): AssetFormRow {
  return {
    existingId: asset.id,
    type: asset.type,
    path: asset.path,
    host: asset.host,
    port: asset.port,
  };
}

function scopeAssetsFromProject(project: WorkProject): AssetFormRow[] {
  const assets = project.assets
    .filter((asset) => asset.origin === WORK_PROJECT_ASSET_ORIGIN.SCOPE)
    .map(assetFromProject);
  return assets.length ? assets : [{ ...EMPTY_ASSET }];
}

function normalizeAsset(asset: AssetFormRow): WorkProjectAssetRequest {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) {
    return { type: asset.type, path: asset.path.trim(), host: "", port: null };
  }
  return {
    type: asset.type,
    path: "",
    host: asset.host.trim(),
    port: asset.type === WORK_PROJECT_ASSET_TYPE.SERVICE ? asset.port : null,
  };
}

function isAssetComplete(asset: WorkProjectAssetRequest): boolean {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) return Boolean(asset.path.trim());
  return Boolean(asset.host.trim());
}

/** 完全没有填写内容的行（只剩类型下拉），批量导入时会被清理掉。 */
function isAssetEmpty(asset: AssetFormRow): boolean {
  return !asset.host.trim() && !asset.path.trim();
}

function resetAssetForType(type: WorkProjectAssetRequest["type"]): Partial<AssetFormRow> {
  return { type, path: "", host: "", port: null };
}

// Label for the `host` input field, which carries a different identifier per asset type.
const ASSET_HOST_FIELD_LABEL: Record<Exclude<WorkProjectAssetRequest["type"], typeof WORK_PROJECT_ASSET_TYPE.BINARY>, string> = {
  [WORK_PROJECT_ASSET_TYPE.SERVICE]: "主机",
  [WORK_PROJECT_ASSET_TYPE.DOMAIN]: "域名",
  [WORK_PROJECT_ASSET_TYPE.NETWORK]: "网段 (CIDR)",
};

// ───────── 批量导入：单行解析与身份判重（对齐后端 WorkProjectAssetRequest 规则）─────────
const ASSET_TYPE = WORK_PROJECT_ASSET_TYPE;
const IPV4_RE = /^\d{1,3}(?:\.\d{1,3}){3}$/;
const IPV6_RE = /^[0-9a-fA-F:]+$/;
const HOST_PORT_RE = /^([^:\s]+):(\d{1,5})$/;
const DOMAIN_RE = /^[a-zA-Z0-9*][a-zA-Z0-9.*_-]*$/;

function parseBulkLine(raw: string): { asset?: WorkProjectAssetRequest; error?: string } {
  const token = raw.trim();
  // 以 / 开头的行是沙箱内绝对路径，按二进制（源码目录 / 文件）资产处理。
  if (token.startsWith("/")) {
    return { asset: { type: ASSET_TYPE.BINARY, host: "", port: null, path: token } };
  }
  if (token.includes(":")) {
    const matched = HOST_PORT_RE.exec(token);
    if (matched) {
      const port = Number(matched[2]);
      if (port < 1 || port > 65535) {
        return { error: `端口超出 1-65535 范围：${matched[2]}` };
      }
      return { asset: { type: ASSET_TYPE.SERVICE, host: matched[1].toLowerCase(), port, path: "" } };
    }
    if (IPV6_RE.test(token)) {
      return { asset: { type: ASSET_TYPE.NETWORK, host: token.toLowerCase(), port: null, path: "" } };
    }
    return { error: "冒号后应为 1-65535 的端口号" };
  }
  if (token.includes("/")) {
    const cidr = normalizeCidrIPv4(token);
    if (!cidr) return { error: "网段格式非法，应形如 10.0.0.0/24" };
    return { asset: { type: ASSET_TYPE.NETWORK, host: cidr, port: null, path: "" } };
  }
  if (IPV4_RE.test(token)) {
    const cidr = normalizeCidrIPv4(`${token}/32`);
    if (!cidr) return { error: "IPv4 地址非法" };
    return { asset: { type: ASSET_TYPE.NETWORK, host: cidr, port: null, path: "" } };
  }
  if (!DOMAIN_RE.test(token)) {
    return { error: "无法识别，应为 主机:端口 / IPv4 / CIDR / /路径 / 域名" };
  }
  return { asset: { type: ASSET_TYPE.DOMAIN, host: token.toLowerCase(), port: null, path: "" } };
}

/** 与后端 build_asset_identifier 保持一致：binary 用路径，service 用 host:port，其余用 host。 */
function assetIdentity(asset: WorkProjectAssetRequest): string {
  if (asset.type === ASSET_TYPE.BINARY) return `binary:${asset.path.trim()}`;
  const host = asset.host.trim().toLowerCase();
  if (asset.type === ASSET_TYPE.SERVICE) return `service:${asset.port ? `${host}:${asset.port}` : host}`;
  if (asset.type === ASSET_TYPE.NETWORK) return `network:${normalizeCidrIPv4(host) ?? host}`;
  return `domain:${host}`;
}

/** 把 IPv4 或 IPv4 CIDR 归一化成后端 ipaddress.ip_network(strict=False) 的写法。 */
function normalizeCidrIPv4(value: string): string | null {
  const [address, prefixText] = value.split("/");
  if (prefixText === undefined || !IPV4_RE.test(address)) return null;
  const prefix = Number(prefixText);
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) return null;
  const octets = address.split(".").map(Number);
  if (octets.some((octet) => octet > 255)) return null;
  const numeric = octets.reduce((total, octet) => total * 256 + octet, 0);
  const size = 2 ** (32 - prefix);
  const network = Math.floor(numeric / size) * size;
  const normalized = [24, 16, 8, 0].map((shift) => Math.floor(network / 2 ** shift) % 256);
  return `${normalized.join(".")}/${prefix}`;
}

function bulkSummary(report: BulkLine[]): string {
  const count = (status: BulkLine["status"]) => report.filter((item) => item.status === status).length;
  const parts = [`已导入 ${count("ok")}`];
  if (count("duplicate")) parts.push(`重复 ${count("duplicate")}`);
  if (count("error")) parts.push(`失败 ${count("error")}`);
  return parts.join(" · ");
}

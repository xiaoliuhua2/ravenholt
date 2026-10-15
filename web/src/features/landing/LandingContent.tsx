import type { ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  Bot,
  Boxes,
  Braces,
  ClipboardCheck,
  Code2,
  Database,
  FileCheck2,
  FileSearch,
  FolderKanban,
  GitBranch,
  Layers3,
  LockKeyhole,
  Network,
  Route,
  ScrollText,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { cx } from "../../shared/lib/className";
import { ThemeSwitcher } from "../../shared/theme/ThemeSwitcher";

const repositoryUrl = "https://github.com/xiaoliuhua2/ravenholt";
const upstreamUrl = "https://github.com/usestrix/strix";
const docsOverviewUrl = "https://github.com/xiaoliuhua2/ravenholt/blob/main/docs/en/guide/overview.md";

type LandingPrimaryAction = {
  label: string;
  href?: string;
  external?: boolean;
  onSelect?: () => void;
};

type LandingContentProps = {
  logoSrc: string;
  primaryAction: LandingPrimaryAction;
};

type CardItem = {
  title: string;
  text: string;
  icon: LucideIcon;
  kicker?: string;
  items?: string[];
};

/** 四层架构：hero 下方的发丝线分隔带 */
const layers: CardItem[] = [
  {
    title: "控制平面",
    text: "用户、会话、项目、智能体、主机与系统配置在这里统一收口，权限与资源边界也在这一层判定。",
    icon: Braces,
    items: ["REST 资源", "WebSocket 会话", "访问控制"],
  },
  {
    title: "运行时平面",
    text: "主管智能体拆解任务并派发给专家智能体，模型输出转为应用级事件，时间线保持连续。",
    icon: Workflow,
    items: ["会话运行时", "智能体关系图", "可回放时间线"],
  },
  {
    title: "证据平面",
    text: "资产是节点、关系是有向边、发现携带证据与影响，全部沉淀在模型上下文之外。",
    icon: FileCheck2,
    items: ["资产与范围", "发现与关系图", "攻击路径"],
  },
  {
    title: "执行平面",
    text: "命令在隔离的沙箱容器内执行，支持后台长任务、输出读取与任务取消。",
    icon: SquareTerminal,
    items: ["沙箱容器执行", "后台任务管理", "技能库集成"],
  },
];

const runtimePath: CardItem[] = [
  { title: "操作台", text: "React 控制台整合对话、项目记录、关系图、终端与文件操作。", icon: Layers3 },
  { title: "控制平面", text: "FastAPI 接收 REST 与 WebSocket 流量，解析会话、项目与用户边界。", icon: Braces },
  { title: "会话运行时", text: "运行时执行选定的智能体关系图，把模型输出转为应用级事件。", icon: Bot },
  { title: "工具层", text: "智能体的动作落到项目记录、技能库、专家委派或沙箱容器。", icon: Workflow },
  { title: "持久化", text: "PostgreSQL 保存时间线帧、项目证据、资源状态与后台任务状态。", icon: Database },
];

const evidenceNodes: CardItem[] = [
  { title: "范围", text: "声明的目标与项目边界", icon: ShieldCheck },
  { title: "资产", text: "服务、域名、网络、二进制文件", icon: Boxes },
  { title: "关系", text: "结构与攻击关系图边", icon: GitBranch },
  { title: "发现", text: "证据、影响、严重度、状态", icon: FileSearch },
  { title: "攻击路径", text: "从访问入口到影响的有序遍历", icon: Route },
  { title: "复核", text: "记录、关系图、时间线回放", icon: ClipboardCheck },
];

const workbenchSurfaces: CardItem[] = [
  { title: "操作台 Playground", text: "实时对话、智能体选择、流式状态、子智能体面板与沙箱容器终端/文件管理。", icon: Activity },
  { title: "工作项目", text: "项目元数据、负责人、范围资产、会话、记录、关系图与攻击路径。", icon: FolderKanban },
  { title: "出口代理", text: "受控网络出口的配置与管理。", icon: Network },
  { title: "策略审批", text: "红线策略下的动作审批与放行。", icon: ShieldCheck },
  { title: "审计日志", text: "关键操作与事件的审计追踪。", icon: ScrollText },
  { title: "系统用户", text: "系统用户与角色权限管理。", icon: Users },
  { title: "系统配置", text: "系统运行参数配置。", icon: Settings },
];

const stats = [
  { value: "04", label: "分层架构", note: "控制 / 运行时 / 证据 / 执行" },
  { value: "100%", label: "时间线可回放", note: "每一步都有证据" },
];

export function LandingContent({ logoSrc, primaryAction }: LandingContentProps) {
  return (
    <main className="lp">
      <img className="lp-watermark" src={logoSrc} alt="" aria-hidden="true" />

      <header className="lp-nav">
        <div className="lp-in lp-nav-in">
          <div className="lp-brand">
            <img src={logoSrc} alt="" />
            <span>RAVENHOLT</span>
          </div>
          <nav className="lp-nav-r" aria-label="主导航">
            <a className="lp-link" href="#architecture">架构</a>
            <a className="lp-link" href="#evidence">证据</a>
            <a className="lp-link" href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub</a>
            <ThemeSwitcher />
            <LandingAction action={primaryAction} variant="ink" />
          </nav>
        </div>
      </header>

      <section className="lp-hero" aria-label="Ravenholt 平台介绍">
        <div className="lp-in">
          <div className="lp-hero-grid">
            <div className="lp-hero-l">
              <span className="lp-kicker">OPEN SOURCE · 授权红队协作</span>
              <h1 className="lp-h1">
                红队智能体<em>·</em>协作平台
              </h1>
              <p className="lp-lede">
                面向授权渗透测试、漏洞挖掘、代码审计与安全研究。多智能体编排、证据沉淀、可回放时间线，全部收敛在一处。
              </p>
              <div className="lp-acts">
                <LandingAction action={primaryAction} variant="ink" />
                <LandingAction
                  action={{ label: "GitHub", href: repositoryUrl, external: true }}
                  variant="line"
                  icon={GitBranch}
                />
              </div>
            </div>

            <aside className="lp-hero-r">
              <dl className="lp-meta">
                <MetaRow term="Version" value="v0.2.1" mono />
                <MetaRow term="Upstream" value="基于 strix 构建" />
                <MetaRow term="Runtime" value="Kali · Docker · PostgreSQL" />
                <MetaRow term="License" value="仅限授权范围使用" />
              </dl>
            </aside>
          </div>
        </div>
      </section>

      <div className="lp-in" id="architecture">
        <div className="lp-arch">
          {layers.map((layer, index) => (
            <div className="lp-arch-cell" key={layer.title}>
              <span className="lp-idx">{String(index + 1).padStart(2, "0")}</span>
              <b>{layer.title}</b>
              <p>{layer.text}</p>
              {layer.items ? (
                <ul>
                  {layer.items.map((entry) => <li key={entry}>{entry}</li>)}
                </ul>
              ) : null}
            </div>
          ))}
        </div>

        <div className="lp-stats">
          {stats.map((stat) => (
            <div className="lp-stat" key={stat.label}>
              <b>{stat.value}</b>
              <span>{stat.label}<i>{stat.note}</i></span>
            </div>
          ))}
        </div>
      </div>

      <Section eyebrow="运行链路" title="实时交互、后台任务与时间线回放共享同一套应用事件模型。">
        <div className="lp-rows">
          {runtimePath.map((item, index) => (
            <div className="lp-row" key={item.title}>
              <span className="lp-row-idx">{String(index + 1).padStart(2, "0")}</span>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        id="evidence"
        eyebrow="证据模型"
        title="WorkProject 把临时的调查产出沉淀为可复核的审查材料。"
        description="资产是关系图节点，关系是有向边，发现携带证据与影响，攻击路径还原访问与影响在图中如何推进。"
      >
        <div className="lp-grid lp-grid-3">
          {evidenceNodes.map((item, index) => (
            <Cell key={item.title} item={item} index={index} />
          ))}
        </div>
      </Section>

      <Section eyebrow="沙箱执行环境" title="命令执行、后台任务与技能库集成，全部在沙箱容器内运行。">
        <div className="lp-note">
          <h3>命令在隔离的沙箱容器中执行，与平台本体隔离。</h3>
          <p>所有 Shell 命令通过 Docker 沙箱容器执行，支持同步执行、后台长任务、输出文件读取与任务取消；容器按会话自动 provision。</p>
          <p>技能库（strix skills）提供结构化的安全分析方法论，智能体可在执行前后按需加载参考。</p>
        </div>
      </Section>

      <Section eyebrow="操作台" title="前端展示与后端控制平面一致的资源模型。">
        <div className="lp-rows">
          {workbenchSurfaces.map((item, index) => (
            <div className="lp-row" key={item.title}>
              <span className="lp-row-idx">{String(index + 1).padStart(2, "0")}</span>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow="使用边界" title="仅限授权使用。">
        <div className="lp-note">
          <p>
            Ravenholt 红队智能体（Ravenholt RedTeam Agent）仅限在合法且获得明确授权的范围内用于安全测试、风险评估、代码审计与研究。不授予测试、扫描、访问或影响任何第三方系统、网络、服务、账户或数据的权限。
          </p>
          <a className="lp-inline-link" href={docsOverviewUrl} target="_blank" rel="noopener noreferrer">
            阅读使用文档
            <ArrowRight size={15} />
          </a>
        </div>
      </Section>

      <footer className="lp-foot">
        <span>
          Ravenholt v0.2.1 · 基于 <a href={upstreamUrl} target="_blank" rel="noopener noreferrer">strix</a> 构建
        </span>
        <span>04 层架构 · 100% 时间线可回放</span>
        <span>仅限授权范围使用</span>
      </footer>
    </main>
  );
}

function Section({
  children,
  description,
  eyebrow,
  id,
  title,
}: {
  children: ReactNode;
  description?: string;
  eyebrow: string;
  id?: string;
  title: string;
}) {
  return (
    <section className="lp-sec" id={id}>
      <div className="lp-in">
        <div className="lp-sec-head">
          <div>
            <span className="lp-eyebrow">{eyebrow}</span>
            <h2 className="lp-h2">{title}</h2>
          </div>
          {description ? <p className="lp-sec-desc">{description}</p> : null}
        </div>
        {children}
      </div>
    </section>
  );
}

function MetaRow({ mono = false, term, value }: { mono?: boolean; term: string; value: string }) {
  return (
    <div className="lp-meta-row">
      <dt>{term}</dt>
      <dd className={cx(mono && "mono")}>{value}</dd>
    </div>
  );
}

function Cell({ index, item }: { index: number; item: CardItem }) {
  const Icon = item.icon;
  return (
    <article className="lp-cell">
      <div className="lp-cell-top">
        <span>{String(index + 1).padStart(2, "0")}</span>
        <Icon size={17} />
      </div>
      <h3>{item.title}</h3>
      <p>{item.text}</p>
    </article>
  );
}

function LandingAction({
  action,
  icon: Icon = ShieldCheck,
  variant = "line",
}: {
  action: LandingPrimaryAction;
  icon?: LucideIcon;
  variant?: "ink" | "line";
}) {
  const className = cx("lp-btn", variant === "ink" && "lp-btn-ink");
  const content = (
    <>
      <Icon size={16} />
      <span>{action.label}</span>
    </>
  );

  if (action.href) {
    return (
      <a
        className={className}
        href={action.href}
        target={action.external ? "_blank" : undefined}
        rel={action.external ? "noopener noreferrer" : undefined}
      >
        {content}
      </a>
    );
  }

  return (
    <button className={className} type="button" onClick={action.onSelect}>
      {content}
    </button>
  );
}

import { Avatar, Button } from "@douyinfe/semi-ui";
import { FolderKanban, FolderPlus, LogOut, MessageSquareCode, Network, ScrollText, Settings, ShieldCheck, Users } from "lucide-react";
import { ReactNode, Suspense, useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { SessionList } from "../../features/playground/SessionList";
import { useContextColumnWidth } from "../../features/playground/useContextColumnWidth";
import { useAgentSessionContext } from "../../features/playground/AgentSessionProvider";
import { usePendingConfirmationCount } from "../../features/policy-confirmations/usePendingConfirmationCount";
import { WorkProjectFormModal } from "../../features/work-projects/WorkProjectFormModal";
import { createWorkProject } from "../../shared/api/workProjects";
import type { CreateWorkProjectRequest } from "../../shared/api/types";
import { useAuth } from "../../shared/auth/AuthProvider";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { cx } from "../../shared/lib/className";
import { ThemeSwitcher } from "../../shared/theme/ThemeSwitcher";
import ravenholtLogo from "../../assets/ravenholt-logo.svg";
import { preloadAdminRoute, preloadAdminRoutes } from "../routePreload";

type AdminLayoutContext = {
  setHeaderActions: (actions: ReactNode) => void;
  refreshWorkProjects: () => void;
};

export function useAdminHeaderActions() {
  return useOutletContext<AdminLayoutContext>().setHeaderActions;
}

export function useRefreshWorkProjects() {
  return useOutletContext<AdminLayoutContext>().refreshWorkProjects;
}

const upstreamUrl = "https://github.com/usestrix/strix";
const versionLabel = "v0.2.1";
const versionTitle = `Ravenholt ${versionLabel} · 基于 strix 构建`;

const navItems = [
  { path: "/playground", label: "操作台", eyebrow: "智能体工作台", icon: MessageSquareCode },
  { path: "/work-projects", label: "工作项目", eyebrow: "项目运营", icon: FolderKanban, adminOnly: true },
  { path: "/egress-proxies", label: "出口代理", eyebrow: "网络出口", icon: Network, adminOnly: true },
  { path: "/policy-confirmations", label: "策略审批", eyebrow: "红线管控", icon: ShieldCheck, adminOnly: true },
  { path: "/audit-events", label: "审计日志", eyebrow: "安全审计", icon: ScrollText, adminOnly: true },
  { path: "/system-users", label: "系统用户", eyebrow: "访问控制", icon: Users, adminOnly: true },
  { path: "/system-config", label: "系统配置", eyebrow: "运行参数", icon: Settings, adminOnly: true },
];

export function AdminLayout() {
  const { signOut, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [headerActions, setHeaderActionsState] = useState<ReactNode>(null);
  const [projectListVersion, setProjectListVersion] = useState(0);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const {
    sessions,
    sessionsLoading,
    activeSessionId,
    selectSession,
    deleteSession,
    refreshSessions,
    dropSessionRuntime,
    syncSessionSummaries,
  } = useAgentSessionContext();

  const setHeaderActions = useCallback((actions: ReactNode) => {
    setHeaderActionsState(() => actions);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(preloadAdminRoutes, 300);
    return () => window.clearTimeout(id);
  }, []);

  const {
    shellRef,
    onResizeStart: onContextResizeStart,
    reset: resetContextWidth,
    collapsed: contextCollapsed,
    toggleCollapsed: toggleContextCollapsed,
  } = useContextColumnWidth();

  const isAdmin = user?.role === "admin";
  // 待确认动作许可数量：仅管理员轮询，用于导航角标提醒。
  const pendingConfirmations = usePendingConfirmationCount(Boolean(isAdmin));

  const refreshWorkProjects = useCallback(() => {
    setProjectListVersion((version) => version + 1);
  }, []);

  const { saving: creatingProject, submit: submitProject } = useResourceSubmit({
    onSuccess: () => {
      setProjectModalOpen(false);
      refreshWorkProjects();
    },
  });

  const handleCreateProject = (payload: CreateWorkProjectRequest) => (
    submitProject(() => createWorkProject(payload))
  );

  const handleSelectAgentSession = useCallback((sessionId: string) => {
    selectSession(sessionId);
    if (!location.pathname.startsWith("/playground")) {
      navigate("/playground");
    }
  }, [location.pathname, navigate, selectSession]);

  const outletContext: AdminLayoutContext = { setHeaderActions, refreshWorkProjects };

  const handleSignOut = () => {
    signOut();
    navigate("/login", { replace: true });
  };

  const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);
  const activeItem = visibleNavItems.find((item) => location.pathname.startsWith(item.path));
  const isPlayground = location.pathname.startsWith("/playground");
  const contentMode = isPlayground ? "fixed" : "scroll";

  return (
    <div ref={shellRef} className={cx("admin-shell", isPlayground && "admin-shell-context")}>
      <aside className="admin-rail">
        <img className="rail-logo" src={ravenholtLogo} alt="Ravenholt" title={versionTitle} />

        <nav className="rail-nav" aria-label="主导航">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const badge = item.path === "/policy-confirmations" ? pendingConfirmations : 0;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className="rail-item"
                title={
                  item.path === "/playground"
                    ? contextCollapsed
                      ? "操作台 · 点击展开会话列"
                      : "操作台 · 再次点击收起会话列"
                    : item.label
                }
                aria-label={item.label}
                onClick={(event) => {
                  // 已处于操作台时，再次点击该图标即折叠/展开会话列，而非重复跳转
                  if (item.path === "/playground" && location.pathname.startsWith("/playground")) {
                    event.preventDefault();
                    toggleContextCollapsed();
                  }
                }}
                onFocus={() => preloadAdminRoute(item.path)}
                onPointerDown={() => preloadAdminRoute(item.path)}
                onPointerEnter={() => preloadAdminRoute(item.path)}
              >
                <Icon size={18} />
                {badge > 0 ? (
                  <span className="rail-item-badge">{badge > 99 ? "99+" : badge}</span>
                ) : null}
              </NavLink>
            );
          })}
        </nav>

        <div className="rail-account">
          <ThemeSwitcher rail />
          <Avatar size="small" color="red">{user?.username?.[0]?.toUpperCase() || "U"}</Avatar>
          <Button icon={<LogOut size={16} />} theme="borderless" type="tertiary" onClick={handleSignOut} aria-label="退出登录" />
        </div>

        <div className="rail-meta" title={versionTitle}>
          <span>{versionLabel}</span>
          <a href={upstreamUrl} target="_blank" rel="noopener noreferrer">strix</a>
        </div>
      </aside>

      {isPlayground ? (
        <section className="admin-context" aria-label="会话">
          <div className="admin-context-head">
            <span>会话</span>
            <em>{sessions.length}</em>
          </div>
          {isAdmin ? (
            <div className="admin-context-actions">
              <Button
                block
                icon={<FolderPlus size={15} />}
                theme="solid"
                type="primary"
                onClick={() => setProjectModalOpen(true)}
              >
                新建项目
              </Button>
            </div>
          ) : null}
          <div className="admin-context-body">
            <SessionList
              sessions={sessions}
              loading={sessionsLoading}
              activeSessionId={activeSessionId}
              projectListVersion={projectListVersion}
              onSelect={handleSelectAgentSession}
              onDelete={deleteSession}
              onRefreshSessions={refreshSessions}
              onDropRuntime={dropSessionRuntime}
              onSyncSessionSummaries={syncSessionSummaries}
            />
          </div>
          <WorkProjectFormModal
            open={projectModalOpen}
            saving={creatingProject}
            onCancel={() => setProjectModalOpen(false)}
            onSubmit={handleCreateProject}
          />
          <div
            className="admin-context-resizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="拖动调整会话列宽度"
            title="拖动调整会话列宽度（双击复位）"
            onPointerDown={onContextResizeStart}
            onDoubleClick={resetContextWidth}
          />
        </section>
      ) : null}

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="topbar-title">
            <div className="page-eyebrow">{activeItem?.eyebrow || "运维"}</div>
            <h1>{activeItem?.label || "控制台"}</h1>
          </div>
          <div className="topbar-actions">
            {headerActions ? <div className="topbar-resource-actions">{headerActions}</div> : null}
          </div>
        </header>
        <main className="admin-content">
          <div className={cx("admin-content-viewport", `admin-content-viewport-${contentMode}`)}>
            <div className={cx("admin-route", `admin-route-${contentMode}`)}>
              <Suspense fallback={<AdminRouteFallback />}>
                <Outlet context={outletContext} />
              </Suspense>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function AdminRouteFallback() {
  return (
    <div className="admin-route-fallback">
      <div className="route-fallback-spinner" />
    </div>
  );
}

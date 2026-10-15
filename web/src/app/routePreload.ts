const routeLoaders = {
  landing: () => import("../features/landing/LandingPage"),
  login: () => import("../features/auth/LoginPage"),
  protectedAdminShell: () => import("./layouts/ProtectedAdminShell"),
  egressProxies: () => import("../features/egress-proxies/EgressProxiesPage"),
  playground: () => import("../features/playground/PlaygroundPage"),
  workProjects: () => import("../features/work-projects/WorkProjectsPage"),
  workProjectWorkspace: () => import("../features/work-projects/WorkProjectWorkspacePage"),
  systemUsers: () => import("../features/system-users/SystemUsersPage"),
  systemConfig: () => import("../features/system-config/SystemConfigPage"),
  policyConfirmations: () => import("../features/policy-confirmations/PolicyConfirmationsPage"),
  auditEvents: () => import("../features/audit-events/AuditEventsPage"),
} as const;

const adminRouteLoaders: Record<string, () => Promise<unknown>> = {
  "/playground": routeLoaders.playground,
  "/egress-proxies": routeLoaders.egressProxies,
  "/work-projects": routeLoaders.workProjects,
  "/work-projects/:projectId": routeLoaders.workProjectWorkspace,
  "/policy-confirmations": routeLoaders.policyConfirmations,
  "/audit-events": routeLoaders.auditEvents,
  "/system-users": routeLoaders.systemUsers,
  "/system-config": routeLoaders.systemConfig,
};

const preloadedRoutes = new Set<string>();

export const loadLandingPage = routeLoaders.landing;
export const loadLoginPage = routeLoaders.login;
export const loadProtectedAdminShell = routeLoaders.protectedAdminShell;
export const loadEgressProxiesPage = routeLoaders.egressProxies;
export const loadPlaygroundPage = routeLoaders.playground;
export const loadWorkProjectsPage = routeLoaders.workProjects;
export const loadWorkProjectWorkspacePage = routeLoaders.workProjectWorkspace;
export const loadSystemUsersPage = routeLoaders.systemUsers;
export const loadSystemConfigPage = routeLoaders.systemConfig;
export const loadPolicyConfirmationsPage = routeLoaders.policyConfirmations;
export const loadAuditEventsPage = routeLoaders.auditEvents;

export function preloadAdminRoute(path: string) {
  const loader = adminRouteLoaders[path];
  if (!loader || preloadedRoutes.has(path)) return;
  preloadedRoutes.add(path);
  void loader().catch(() => preloadedRoutes.delete(path));
}

export function preloadAdminRoutes() {
  for (const path of Object.keys(adminRouteLoaders)) {
    preloadAdminRoute(path);
  }
}

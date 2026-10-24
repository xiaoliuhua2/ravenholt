import { Button, Popconfirm, Progress } from "@douyinfe/semi-ui";
import {
  Ban,
  ChevronDown,
  ChevronRight,
  Edit3,
  FolderKanban,
  FolderOpen,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRefreshWorkProjects } from "../../app/layouts/AdminLayout";
import { WORK_PROJECT_STATUS } from "../../shared/api/contract";
import {
  cancelWorkProject,
  createWorkProject,
  deleteWorkProject,
  queryWorkProjects,
  retryWorkProject,
  updateWorkProjectMetadata,
} from "../../shared/api/workProjects";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type {
  CreateWorkProjectRequest,
  WorkProject,
} from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { ResourceIdentity, ResourceText, RowActions } from "../../shared/components/ResourceCells";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { formatDateTime } from "../../shared/lib/date";
import { UI_TEXT } from "../../shared/lib/uiText";
import { WorkProjectFormModal } from "./WorkProjectFormModal";
import {
  WorkProjectAssets,
  WorkProjectPanel,
  WorkProjectStatusTag,
  WorkProjectSummaries,
  WorkProjectTasks,
  WorkProjectTypeTag,
  workProjectOwnerNames,
} from "./workProjectView";

type AdminAction = "cancel" | "retry" | "delete";

export function WorkProjectsPage() {
  const {
    items: projects, page, keyword, loading, loadItems: loadProjects, total, rangeStart, rangeEnd,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<WorkProject>({ query: queryWorkProjects });
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<WorkProject | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const refreshProjectSidebar = useRefreshWorkProjects();
  const navigate = useNavigate();
  const [adminAction, setAdminAction] = useState<{ id: number; type: AdminAction } | null>(null);

  const refreshAll = useCallback(async () => {
    await loadProjects();
  }, [loadProjects]);

  useAdminResourceHeader({
    createLabel: "创建项目",
    refreshLabel: "刷新工作项目",
    loading,
    onCreate: () => {
      setEditingProject(null);
      setModalOpen(true);
    },
    onRefresh: refreshAll,
  });

  const { saving, submit } = useResourceSubmit({
    onSuccess: async () => {
      setModalOpen(false);
      setEditingProject(null);
      await refreshAll();
      refreshProjectSidebar();
    },
  });

  const summary = useMemo(
    () => projects.reduce(
      (acc, project) => ({
        working: acc.working + (project.status === WORK_PROJECT_STATUS.WORKING ? 1 : 0),
        sessions: acc.sessions + project.session_count,
        assets: acc.assets + project.asset_count,
      }),
      { working: 0, sessions: 0, assets: 0 },
    ),
    [projects],
  );

  const handleSubmit = (payload: CreateWorkProjectRequest) => submit(() => (
    editingProject
      ? updateWorkProjectMetadata(editingProject.id, payload)
      : createWorkProject(payload)
  ));

  const toggleProject = (project: WorkProject) => setExpandedId((current) => (
    current === project.id ? null : project.id
  ));

  const handleAdminProjectAction = async (
    project: WorkProject,
    type: AdminAction,
  ) => {
    setAdminAction({ id: project.id, type });
    try {
      const response = type === "cancel"
        ? await cancelWorkProject(project.id)
        : type === "retry"
          ? await retryWorkProject(project.id)
          : await deleteWorkProject(project.id);
      showApiSuccess(response);
      if (type === "delete") {
        setExpandedId((current) => (current === project.id ? null : current));
      }
      await loadProjects();
      refreshProjectSidebar();
    } catch (error) {
      showApiError(error);
    } finally {
      setAdminAction(null);
    }
  };

  const columns: ResourceColumn<WorkProject>[] = [
    {
      key: "project", header: "项目", width: "minmax(210px, 0.9fr)",
      render: (project) => (
        <ResourceIdentity
          before={(
            <Button
              icon={expandedId === project.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              theme="borderless"
              type="tertiary"
              size="small"
              onClick={() => toggleProject(project)}
              aria-label={`${expandedId === project.id ? "折叠" : "展开"} ${project.name}`}
            />
          )}
          icon={<FolderKanban size={18} />}
          title={project.name}
          detail={`${workProjectOwnerNames(project)} · ${project.session_count} 个会话`}
        />
      ),
    },
    { key: "type", header: "类型", width: "132px", render: (project) => <WorkProjectTypeTag project={project} /> },
    { key: "status", header: "状态", width: "104px", render: (project) => <WorkProjectStatusTag project={project} /> },
    {
      key: "records", header: "记录", width: "minmax(170px, 0.5fr)",
      render: (project) => <ResourceText>{project.asset_count} 个资产 · {project.tasks.length} 个任务</ResourceText>,
    },
    { key: "updated", header: "更新时间", width: "minmax(150px, 0.4fr)", render: (p) => formatDateTime(p.updated_at) },
    {
      key: "actions", header: "操作", width: "132px",
      render: (project) => (
        <RowActions>
          <Button
            icon={<FolderOpen size={15} />}
            theme="borderless"
            type="tertiary"
            aria-label={`打开 ${project.name} 的工作区`}
            onClick={() => navigate(`/work-projects/${project.id}`)}
          />
          <Button
            icon={<Edit3 size={15} />}
            theme="borderless"
            type="tertiary"
            aria-label={`编辑 ${project.name}`}
            onClick={() => { setEditingProject(project); setModalOpen(true); }}
          />
          <Button
            icon={<Ban size={15} />}
            theme="borderless"
            type="danger"
            disabled={!project.can_cancel}
            loading={adminAction?.id === project.id && adminAction.type === "cancel"}
            aria-label={`取消 ${project.name}`}
            onClick={() => void handleAdminProjectAction(project, "cancel")}
          />
          <Button
            icon={<RotateCcw size={15} />}
            theme="borderless"
            type="tertiary"
            disabled={!project.can_retry}
            loading={adminAction?.id === project.id && adminAction.type === "retry"}
            aria-label={`重试 ${project.name}`}
            onClick={() => void handleAdminProjectAction(project, "retry")}
          />
          <Popconfirm title="删除项目" content={`删除 ${project.name} 及其所有项目会话？`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void handleAdminProjectAction(project, "delete")}>
            <Button
              icon={<Trash2 size={15} />}
              theme="borderless"
              type="danger"
              loading={adminAction?.id === project.id && adminAction.type === "delete"}
              aria-label={`删除 ${project.name}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  const expandedProject = projects.find((project) => project.id === expandedId) ?? null;

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="搜索项目名称、类型、描述或状态"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "总数", value: total },
          { label: "进行中", value: summary.working },
          { label: "项目会话", value: summary.sessions },
          { label: "资产", value: summary.assets },
        ]}
        empty={projects.length === 0}
        emptyIcon={<FolderKanban size={42} />}
        emptyTitle="暂无项目"
        page={page}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        total={total}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<WorkProject>
          ariaLabel="工作项目"
          className="work-projects-table"
          columns={columns}
          rows={projects}
          rowKey={(project) => project.id}
        />
        {expandedProject ? (
          <WorkProjectExpanded project={expandedProject} />
        ) : null}
      </ResourcePageShell>

      <WorkProjectFormModal
        open={modalOpen}
        saving={saving}
        project={editingProject}
        onCancel={() => { setModalOpen(false); setEditingProject(null); }}
        onSubmit={handleSubmit}
      />
    </>
  );
}

function WorkProjectExpanded({
  project,
}: {
  project: WorkProject;
}) {
  return (
    <div className="work-project-expanded">
      <section className="work-project-meta">
        <div>
          <span>负责人</span>
          <strong>{workProjectOwnerNames(project)}</strong>
        </div>
        <div>
          <span>沙箱</span>
          <strong>{project.sandbox_container_ids.length || "-"}</strong>
        </div>
        <div>
          <span>任务进度</span>
          <Progress percent={project.progress} size="small" showInfo />
        </div>
      </section>

      <section className="work-project-detail-grid">
        <WorkProjectPanel title="资产" empty={project.asset_count === 0 ? "暂无资产。" : ""}>
          <WorkProjectAssets project={project} />
        </WorkProjectPanel>
        <WorkProjectPanel title="任务" empty={project.tasks.length === 0 ? "暂无任务。" : ""}>
          <WorkProjectTasks project={project} />
        </WorkProjectPanel>
        <WorkProjectPanel title="Agent 摘要" empty={project.agent_summaries.length === 0 ? "暂无摘要。" : ""}>
          <WorkProjectSummaries project={project} />
        </WorkProjectPanel>
      </section>
    </div>
  );
}

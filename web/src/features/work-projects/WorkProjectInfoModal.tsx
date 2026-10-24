import { Empty, Modal, Progress, Spin } from "@douyinfe/semi-ui";
import { FileText, UserRound } from "lucide-react";
import type { WorkProject } from "../../shared/api/types";
import { type ProjectRecordTab, WorkProjectRecordTabs } from "./ProjectRecordViews";
import { useWorkProjectRecordSnapshot } from "./workProjectRecords";
import {
  WorkProjectPanel,
  WorkProjectStatusTag,
  WorkProjectSummaries,
  WorkProjectTasks,
  WorkProjectTypeTag,
  workProjectOwnerNames,
} from "./workProjectView";

type WorkProjectInfoModalProps = {
  open: boolean;
  projectId: number | null;
  initialTab?: ProjectRecordTab;
  onClose: () => void;
};

export function WorkProjectInfoModal({ open, projectId, initialTab = "assets", onClose }: WorkProjectInfoModalProps) {
  const { project, records, loading } = useWorkProjectRecordSnapshot(projectId, open);

  return (
    <Modal
      visible={open}
      centered
      className="project-info-modal"
      title={<ProjectInfoTitle project={project} />}
      width="min(1440px, calc(100vw - 24px))"
      footer={null}
      onCancel={onClose}
    >
      <Spin spinning={loading}>
        {project ? (
          <div className="project-info-content project-record-content">
            <section className="project-info-main">
              <section className="project-info-meta">
                <div>
                  <span>类型</span>
                  <WorkProjectTypeTag project={project} />
                </div>
                <div>
                  <span>状态</span>
                  <WorkProjectStatusTag project={project} />
                </div>
                <div>
                  <span>负责人</span>
                  <strong>{workProjectOwnerNames(project)}</strong>
                </div>
                <div>
                  <span>沙箱</span>
                  <strong>{project.sandbox_container_ids.length || "-"}</strong>
                </div>
              </section>

              {project.description ? <div className="project-info-description">{project.description}</div> : null}

              <section className="project-info-progress">
                <span>任务进度</span>
                <Progress percent={project.progress} size="small" showInfo />
              </section>

              <WorkProjectPanel
                title="任务"
                icon={<FileText size={15} />}
                empty={!project.tasks.length ? "暂无数据。" : ""}
                mode="info"
              >
                <WorkProjectTasks project={project} mode="info" />
              </WorkProjectPanel>

              <WorkProjectPanel
                title="Agent 摘要"
                icon={<UserRound size={15} />}
                empty={!project.agent_summaries.length ? "暂无数据。" : ""}
                mode="info"
              >
                <WorkProjectSummaries project={project} mode="info" />
              </WorkProjectPanel>
            </section>

            <section className="project-record-panel">
              <WorkProjectRecordTabs
                records={records}
                initialTab={initialTab}
                projectId={projectId ?? undefined}
              />
            </section>
          </div>
        ) : (
          <Empty className="empty-state" image={<FileText size={42} />} title="未选择项目。" description="" />
        )}
      </Spin>
    </Modal>
  );
}

function ProjectInfoTitle({ project }: { project: WorkProject | null }) {
  return (
    <div className="project-info-title">
      <strong>{project?.name ?? "工作项目"}</strong>
    </div>
  );
}

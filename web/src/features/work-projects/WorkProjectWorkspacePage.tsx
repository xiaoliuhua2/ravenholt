import { Button, Empty, Spin } from "@douyinfe/semi-ui";
import { ArrowLeft, FileText } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MetricStrip } from "../../shared/components/ResourcePageShell";
import { WorkProjectRecordTabs } from "./ProjectRecordViews";
import { useWorkProjectRecordSnapshot } from "./workProjectRecords";
import { workProjectOwnerNames, WorkProjectStatusTag, WorkProjectTypeTag } from "./workProjectView";

export function WorkProjectWorkspacePage() {
  const params = useParams();
  const navigate = useNavigate();
  const projectId = Number(params.projectId);
  const validProjectId = Number.isFinite(projectId) && projectId > 0 ? projectId : null;
  const { project, records, loading } = useWorkProjectRecordSnapshot(validProjectId);

  const metrics = useMemo(() => [
    { label: "资产", value: records.assets.length },
    { label: "发现", value: records.findings.length },
    { label: "关系", value: records.graph.edges.length },
    { label: "会话", value: project?.session_count ?? 0 },
  ], [project, records]);

  if (!validProjectId) {
    return <Empty className="empty-state" image={<FileText size={42} />} title="无效项目" description="" />;
  }

  return (
    <section className="work-project-workspace">
      <div className="workspace-back-row">
        <Button icon={<ArrowLeft size={15} />} theme="borderless" type="tertiary" onClick={() => navigate("/work-projects")}>
          返回
        </Button>
      </div>
      <div className="workspace-header">
        {project ? (
          <div className="workspace-title">
            <div className="workspace-title-main">
              <h2>{project.name}</h2>
              {project.description ? <p>{project.description}</p> : null}
              <span>负责人：{workProjectOwnerNames(project)}</span>
            </div>
            <div className="workspace-title-tags">
              <WorkProjectTypeTag project={project} />
              <WorkProjectStatusTag project={project} />
            </div>
          </div>
        ) : null}
      </div>

      <MetricStrip metrics={metrics} />

      <Spin spinning={loading}>
        <WorkProjectRecordTabs records={records} projectId={validProjectId} className="workspace-tabs" />
      </Spin>
    </section>
  );
}

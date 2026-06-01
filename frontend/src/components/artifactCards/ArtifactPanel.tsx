import type { Artifact, Conversation, WorkspacePreview } from '../../types/api'
import { ArtifactRenderer } from './ArtifactRenderer'

/** 右侧产物面板组件的入参。 */
type ArtifactPanelProps = {
  /** 当前会话，用于展示 workspace_id；为空时说明尚未选择会话。 */
  conversation: Conversation | null
  /** 从当前会话所有消息中聚合出来的 Artifact 列表。 */
  artifacts: Artifact[]
  /** 当前 workspace 的预览状态。 */
  preview: WorkspacePreview | null
  /** 已经成功应用的 diff artifact ID 集合。 */
  appliedDiffIds: ReadonlySet<string>
  /** 当前正在应用的 diff artifact ID。 */
  applyingDiffId: string | null
  /** 点击 Apply Diff 时调用，父组件负责请求 API 和刷新 Preview。 */
  onApplyDiff: (artifact: Artifact, diff: string) => Promise<void>
}

/**
 * 右侧 Artifact 与 Preview 聚合面板。
 * 目标是让 Demo 评委不用翻消息，也能看到当前会话产出的结构化结果。
 */
export function ArtifactPanel({
  conversation,
  artifacts,
  preview,
  appliedDiffIds,
  applyingDiffId,
  onApplyDiff,
}: ArtifactPanelProps) {
  return (
    <section className="artifact-panel">
      {/* 面板标题区，说明右栏展示结构化产物。 */}
      <header className="panel-header">
        <p className="eyebrow">Artifacts</p>
        <h2>产物与预览</h2>
      </header>

      {/* workspace preview 状态卡：和当前会话的 workspace_id 绑定。 */}
      <div className="preview-card">
        <div>
          <span className="preview-label">Workspace</span>
          <strong>{conversation?.workspace_id ?? '未选择'}</strong>
        </div>
        <span
          className={`status-pill status-${preview?.status ?? 'not_started'}`}
        >
          {preview?.status ?? 'not_started'}
        </span>
      </div>

      <div className="artifact-list">
        {artifacts.length === 0 ? (
          <div className="empty-artifacts">当前会话还没有结构化产物。</div>
        ) : (
          artifacts.map((artifact) => (
            // 每个 artifact 复用统一渲染器，保证右侧面板和聊天内联展示一致。
            <ArtifactRenderer
              appliedDiffIds={appliedDiffIds}
              applyingDiffId={applyingDiffId}
              artifact={artifact}
              key={artifact.id}
              onApplyDiff={onApplyDiff}
            />
          ))
        )}
      </div>
    </section>
  )
}

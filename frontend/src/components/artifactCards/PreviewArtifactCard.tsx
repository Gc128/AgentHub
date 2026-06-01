import type { Artifact } from '../../types/api'
import { getArtifactString } from './artifactData'

type PreviewArtifactCardProps = {
  /** preview 类型的 Artifact，data 中应包含 workspace_id/status，可选 preview_url。 */
  artifact: Artifact
}

/**
 * Preview 产物卡片。
 * 当前后端尚未明确 preview_url，所以卡片同时支持状态展示和未来 iframe 预览。
 */
export function PreviewArtifactCard({ artifact }: PreviewArtifactCardProps) {
  const workspaceId = getArtifactString(artifact, 'workspace_id', 'unknown')
  const status = getArtifactString(artifact, 'status', 'not_started')
  const checkedAt = getArtifactString(artifact, 'checked_at')
  const previewUrl = getArtifactString(artifact, 'preview_url')

  return (
    <article className="artifact-card artifact-card-preview">
      <header className="artifact-card-top">
        <div>
          <span className="artifact-type">{artifact.type}</span>
          <h3>{artifact.title}</h3>
        </div>
        <span className={`status-pill status-${status}`}>{status}</span>
      </header>
      <div className="preview-detail-grid">
        <div>
          <span className="preview-label">Workspace</span>
          <strong>{workspaceId}</strong>
        </div>
        <div>
          <span className="preview-label">Checked</span>
          <strong>{checkedAt || '等待刷新'}</strong>
        </div>
      </div>
      {previewUrl ? (
        <iframe
          className="preview-frame"
          src={previewUrl}
          title={`${workspaceId} preview`}
        />
      ) : (
        <div className="preview-placeholder">
          当前文档未明确 preview_url，先展示 workspace 状态。
        </div>
      )}
    </article>
  )
}

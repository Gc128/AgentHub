import {
  ClockCircleOutlined,
  CodeOutlined,
  FileTextOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { Badge, Empty, Tag } from 'antd'
import type {
  AppliedDiffRecord,
  Conversation,
  WorkspaceFile,
  WorkspacePreview,
} from '../../types/api'
import { parseDiffLines } from '../artifactCards/diffLines'

type WorkspacePanelProps = {
  /** 当前会话，用于展示 workspace 归属。 */
  conversation: Conversation | null
  /** 当前 workspace preview 状态。 */
  preview: WorkspacePreview | null
  /** 当前 workspace 文件列表。 */
  files: WorkspaceFile[]
  /** 当前 workspace 已应用 Diff 历史。 */
  appliedDiffs: AppliedDiffRecord[]
}

const getPreviewBadgeStatus = (
  status: WorkspacePreview['status'] | undefined,
): 'success' | 'processing' | 'default' | 'error' | 'warning' => {
  if (status === 'ready') {
    return 'success'
  }

  if (status === 'running') {
    return 'processing'
  }

  if (status === 'error') {
    return 'error'
  }

  return 'default'
}

const formatTime = (value: string | undefined) => {
  if (!value) {
    return '未记录'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

const getDiffSummary = (diff: string) => {
  const added = diff.split('\n').filter((line) => line.startsWith('+') && !line.startsWith('+++'))
  const removed = diff
    .split('\n')
    .filter((line) => line.startsWith('-') && !line.startsWith('---'))
  return `+${added.length} / -${removed.length}`
}

/**
 * 右侧 workspace 面板。
 * 这里只展示当前工作区状态，不重复聊天流中的 Agent 回复内容。
 */
export function WorkspacePanel({
  conversation,
  preview,
  files,
  appliedDiffs,
}: WorkspacePanelProps) {
  const workspaceId = conversation?.workspace_id ?? '未选择'
  const previewStatus = preview?.status ?? 'not_started'

  return (
    <section className="workspace-panel">
      <header className="panel-header">
        <p className="eyebrow">Workspace</p>
        <h2>预览与变更</h2>
      </header>

      <div className="preview-card">
        <div>
          <span className="preview-label">Workspace</span>
          <strong>{workspaceId}</strong>
        </div>
        <Badge
          className={`status-pill status-${previewStatus}`}
          status={getPreviewBadgeStatus(preview?.status)}
          text={previewStatus}
        />
      </div>

      {preview?.preview_url ? (
        <iframe
          className="workspace-preview-frame"
          src={preview.preview_url}
          title={`${workspaceId} preview`}
        />
      ) : (
        <div className="workspace-empty-panel">
          当前 workspace 还没有 preview_url。
        </div>
      )}

      <section className="workspace-section">
        <div className="workspace-section-title">
          <FileTextOutlined />
          <h3>文件</h3>
          <Tag>{files.length}</Tag>
        </div>
        {files.length === 0 ? (
          <Empty
            className="empty-artifacts"
            description="当前 workspace 暂无文件。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div className="workspace-file-list">
            {files.map((file) => (
              <div className="workspace-file-row" key={file.path}>
                <CodeOutlined />
                <div>
                  <strong>{file.path}</strong>
                  <span>{formatTime(file.updated_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-section">
        <div className="workspace-section-title">
          <HistoryOutlined />
          <h3>变更历史</h3>
          <Tag>{appliedDiffs.length}</Tag>
        </div>
        {appliedDiffs.length === 0 ? (
          <Empty
            className="empty-artifacts"
            description="还没有应用过 Diff。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div className="workspace-change-list">
            {appliedDiffs.map((diff) => (
              <article className="workspace-change-row" key={diff.id}>
                <div className="workspace-change-summary">
                  <div>
                    <strong>{diff.path ?? diff.artifact_id}</strong>
                    <span>
                      <ClockCircleOutlined /> {formatTime(diff.applied_at)}
                    </span>
                  </div>
                  <Tag>{getDiffSummary(diff.diff)}</Tag>
                </div>
                <div className="diff-viewer workspace-diff-viewer">
                  {parseDiffLines(diff.diff).map((line, index) => (
                    <pre
                      className={`diff-line diff-line-${line.kind}`}
                      key={`${diff.id}-${index}-${line.content}`}
                    >
                      {line.content || ' '}
                    </pre>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}

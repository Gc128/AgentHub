import {
  ClockCircleOutlined,
  CodeOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { Alert, Badge, Button, Empty, Modal, Popconfirm, Tabs, Tag, Tooltip } from 'antd'
import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type {
  AppliedDiffRecord,
  Conversation,
  WorkspaceFile,
  WorkspaceFileContent,
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
  /** 当前正在删除的文件路径。 */
  deletingFilePath: string | null
  /** 读取文件内容，用于打开预览弹窗。 */
  onPreviewFile: (file: WorkspaceFile) => Promise<WorkspaceFileContent>
  /** 删除真实 workspace 文件。 */
  onDeleteFile: (file: WorkspaceFile) => Promise<void>
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

const isHtmlFile = (path: string) => path.toLowerCase().endsWith('.html')

const getSourceLanguage = (path: string) => {
  const extension = path.split('.').pop()?.toLowerCase()
  return (
    {
      css: 'css',
      html: 'html',
      js: 'javascript',
      json: 'json',
      md: 'markdown',
      py: 'python',
      ts: 'typescript',
      tsx: 'tsx',
    }[extension ?? ''] ?? 'text'
  )
}

const renderSourcePreview = (file: WorkspaceFileContent) => (
  <div className="workspace-source-preview">
    <SyntaxHighlighter
      customStyle={{ background: 'transparent', margin: 0, padding: 0 }}
      language={getSourceLanguage(file.path)}
      PreTag="div"
      showLineNumbers={file.content.split('\n').length > 8}
      style={oneLight}
      wrapLongLines
    >
      {file.content || ' '}
    </SyntaxHighlighter>
  </div>
)

const renderFilePreview = (
  file: WorkspaceFileContent,
  previewUrl: string | undefined,
) => {
  if (!isHtmlFile(file.path)) {
    return renderSourcePreview(file)
  }

  return (
    <Tabs
      items={[
        {
          key: 'preview',
          label: '预览',
          children: (
            previewUrl ? (
              <iframe
                className="workspace-file-preview-frame"
                sandbox="allow-scripts allow-forms"
                src={previewUrl}
                title={`${file.path} preview`}
              />
            ) : (
              <div className="workspace-empty-panel">
                当前 workspace 还没有 preview_url。
              </div>
            )
          ),
        },
        {
          key: 'source',
          label: '源码',
          children: renderSourcePreview(file),
        },
      ]}
    />
  )
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
  deletingFilePath,
  onPreviewFile,
  onDeleteFile,
}: WorkspacePanelProps) {
  const workspaceId = conversation?.workspace_id ?? '未选择'
  const previewStatus = preview?.status ?? 'not_started'
  const [previewFile, setPreviewFile] = useState<WorkspaceFileContent | null>(
    null,
  )
  const [previewLoadingPath, setPreviewLoadingPath] = useState<string | null>(
    null,
  )
  const [fileActionError, setFileActionError] = useState<string | null>(null)
  const [workspacePreviewOpen, setWorkspacePreviewOpen] = useState(false)

  const handlePreviewFile = async (file: WorkspaceFile) => {
    setPreviewLoadingPath(file.path)
    setFileActionError(null)
    try {
      setPreviewFile(await onPreviewFile(file))
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '读取文件失败',
      )
    } finally {
      setPreviewLoadingPath(null)
    }
  }

  const handleDeleteFile = async (file: WorkspaceFile) => {
    setFileActionError(null)
    try {
      await onDeleteFile(file)
      if (previewFile?.path === file.path) {
        setPreviewFile(null)
      }
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '删除文件失败',
      )
    }
  }

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

      <div className="workspace-preview-action">
        <span>
          {preview?.preview_url
            ? '预览已就绪'
            : '当前 workspace 还没有 preview_url。'}
        </span>
        <Button
          disabled={!preview?.preview_url}
          icon={<EyeOutlined />}
          onClick={() => setWorkspacePreviewOpen(true)}
          size="small"
        >
          打开预览
        </Button>
      </div>

      <section className="workspace-section workspace-files-section">
        <div className="workspace-section-title">
          <FileTextOutlined />
          <h3>文件</h3>
          <Tag>{files.length}</Tag>
        </div>
        {fileActionError ? (
          <Alert
            className="workspace-file-error"
            showIcon
            title={fileActionError}
            type="error"
          />
        ) : null}
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
                <div className="workspace-file-info">
                  <strong>{file.path}</strong>
                  <span>{formatTime(file.updated_at)}</span>
                </div>
                <div className="workspace-file-actions">
                  <Tooltip title="预览文件">
                    <Button
                      aria-label={`预览 ${file.path}`}
                      icon={<EyeOutlined />}
                      loading={previewLoadingPath === file.path}
                      onClick={() => void handlePreviewFile(file)}
                      size="small"
                      type="text"
                    />
                  </Tooltip>
                  <Popconfirm
                    cancelText="取消"
                    description={`删除 ${file.path} 后将从当前 workspace 移除。`}
                    okButtonProps={{ danger: true }}
                    okText="删除"
                    onConfirm={() => void handleDeleteFile(file)}
                    title="删除文件？"
                  >
                    <Button
                      aria-label={`删除 ${file.path}`}
                      danger
                      icon={<DeleteOutlined />}
                      loading={deletingFilePath === file.path}
                      size="small"
                      type="text"
                    />
                  </Popconfirm>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-section workspace-change-section">
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
      <Modal
        footer={null}
        onCancel={() => setPreviewFile(null)}
        open={previewFile !== null}
        title={previewFile?.path}
        width={860}
      >
        {previewFile ? renderFilePreview(previewFile, preview?.preview_url) : null}
      </Modal>
      <Modal
        footer={null}
        onCancel={() => setWorkspacePreviewOpen(false)}
        open={workspacePreviewOpen}
        title={`${workspaceId} 预览`}
        width={1040}
      >
        {preview?.preview_url ? (
          <iframe
            className="workspace-modal-preview-frame"
            sandbox="allow-scripts allow-forms"
            src={preview.preview_url}
            title={`${workspaceId} full preview`}
          />
        ) : null}
      </Modal>
    </section>
  )
}

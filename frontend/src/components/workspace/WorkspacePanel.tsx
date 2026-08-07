import {
  ClockCircleOutlined,
  CodeOutlined,
  DeleteOutlined,
  EyeOutlined,
  ExportOutlined,
  FileTextOutlined,
  HistoryOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import { Alert, Badge, Button, Empty, Modal, Popconfirm, Tabs, Tag, Tooltip } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type {
  AppliedDiffRecord,
  ChangeSet,
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
  changeSets: ChangeSet[]
  /** 当前 workspace 展示刷新版本，用于避免 iframe 复用旧资源。 */
  workspaceRefreshToken: number
  /** 当前正在删除的文件路径。 */
  deletingFilePath: string | null
  /** 当前正在回退的 Change Set 或旧 applied diff ID。 */
  revertingDiffRecordId: string | null
  reapplyingChangeSetId: string | null
  reReviewingChangeSetId: string | null
  promotingChangeSetId: string | null
  /** 读取文件内容，用于打开预览弹窗。 */
  onPreviewFile: (file: WorkspaceFile) => Promise<WorkspaceFileContent>
  /** 生成某个 workspace 文件对应的 HTML 预览 URL。 */
  getFilePreviewUrl: (path?: string) => string
  getCandidatePreviewUrl: (changeSetId: string, path?: string) => string
  /** 删除真实 workspace 文件。 */
  onDeleteFile: (file: WorkspaceFile) => Promise<void>
  /** 回退已应用 diff。 */
  onRevertAppliedDiff: (record: AppliedDiffRecord) => Promise<void>
  onRevertChangeSet: (changeSetId: string) => Promise<void>
  onReapplyChangeSet: (changeSetId: string) => Promise<void>
  onReReviewChangeSet: (changeSetId: string) => Promise<void>
  onPromoteChangeSet: (changeSetId: string) => Promise<void>
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

const getPreviewStatusLabel = (
  status: WorkspacePreview['status'] | undefined,
) =>
  ({
    error: '异常',
    not_started: '未开始',
    ready: '就绪',
    running: '运行中',
  })[status ?? 'not_started'] ?? status ?? '未开始'

const getChangeSetStatusLabel = (status: ChangeSet['status']) =>
  ({
    conflicted: '冲突',
    failed: '审查失败',
    generated: '已生成',
    needs_fix: '待修复',
    promoted: '已合入',
    promoting: '合入中',
    ready: '可合入',
    rejected: '已拒绝',
    staging: '隔离准备中',
    validating: '审查中',
  })[status] ?? status

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

type AppliedDiffGroup = {
  id: string
  changeSetId: string | null
  records: AppliedDiffRecord[]
}

const groupAppliedDiffs = (records: AppliedDiffRecord[]): AppliedDiffGroup[] => {
  const groups = new Map<string, AppliedDiffGroup>()
  records.forEach((record) => {
    const id = record.change_set_id ?? `legacy:${record.id}`
    const existing = groups.get(id)
    if (existing) {
      existing.records.push(record)
      return
    }
    groups.set(id, {
      id,
      changeSetId: record.change_set_id ?? null,
      records: [record],
    })
  })
  return [...groups.values()].sort(
    (left, right) =>
      new Date(right.records[0].applied_at).getTime() -
      new Date(left.records[0].applied_at).getTime(),
  )
}

const isHtmlFile = (path: string) => path.toLowerCase().endsWith('.html')
const WORKSPACE_PREVIEW_MODAL_WIDTH = 1280

const hasCompleteCandidateSnapshot = (changeSet: ChangeSet) =>
  changeSet.files.length > 0 &&
  changeSet.files.every(
    (file) => file.operation === 'delete' || typeof file.after_content === 'string',
  )

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
  filePreviewUrl: string,
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
            filePreviewUrl ? (
              <iframe
                key={filePreviewUrl}
                className="workspace-file-preview-frame"
                sandbox="allow-scripts allow-forms allow-same-origin allow-modals"
                src={filePreviewUrl}
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
  changeSets,
  workspaceRefreshToken,
  deletingFilePath,
  revertingDiffRecordId,
  reapplyingChangeSetId,
  reReviewingChangeSetId,
  promotingChangeSetId,
  onPreviewFile,
  getFilePreviewUrl,
  getCandidatePreviewUrl,
  onDeleteFile,
  onRevertAppliedDiff,
  onRevertChangeSet,
  onReapplyChangeSet,
  onReReviewChangeSet,
  onPromoteChangeSet,
}: WorkspacePanelProps) {
  const workspaceId = conversation?.workspace_id ?? '未选择'
  const previewStatus = preview?.status ?? 'not_started'
  const previewStatusLabel = getPreviewStatusLabel(previewStatus)
  const [previewFile, setPreviewFile] = useState<WorkspaceFileContent | null>(
    null,
  )
  const [previewLoadingPath, setPreviewLoadingPath] = useState<string | null>(
    null,
  )
  const [fileActionError, setFileActionError] = useState<string | null>(null)
  const [previewingCandidateId, setPreviewingCandidateId] = useState<string | null>(null)
  const onPreviewFileRef = useRef(onPreviewFile)
  const previewFilePath = previewFile?.path
  const workspacePreviewUrl = preview?.preview_url
    ? getFilePreviewUrl(preview.entry_path ?? undefined)
    : ''
  const candidateChangeSets = changeSets.filter(
    (item) => !['promoted', 'rejected'].includes(item.status),
  )
  const appliedDiffGroups = groupAppliedDiffs(appliedDiffs)
  const previewingCandidate = changeSets.find(
    (item) => item.id === previewingCandidateId,
  )
  const candidatePreviewUrl =
    previewingCandidate?.entry_path && previewingCandidateId
      ? getCandidatePreviewUrl(
          previewingCandidateId,
          previewingCandidate.entry_path,
        )
      : ''
  useEffect(() => {
    onPreviewFileRef.current = onPreviewFile
  }, [onPreviewFile])

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

  const handleRevertAppliedDiff = async (record: AppliedDiffRecord) => {
    setFileActionError(null)
    try {
      await onRevertAppliedDiff(record)
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '回退 Diff 失败',
      )
    }
  }

  const handleRevertChangeSet = async (changeSetId: string) => {
    setFileActionError(null)
    try {
      await onRevertChangeSet(changeSetId)
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '整组回退失败',
      )
    }
  }

  const handleReapplyChangeSet = async (changeSetId: string) => {
    setFileActionError(null)
    try {
      await onReapplyChangeSet(changeSetId)
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '重新应用失败',
      )
    }
  }

  const handlePromoteChangeSet = async (changeSetId: string) => {
    setFileActionError(null)
    try {
      await onPromoteChangeSet(changeSetId)
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '合入 Workspace 失败',
      )
    }
  }

  const handleReReviewChangeSet = async (changeSetId: string) => {
    setFileActionError(null)
    try {
      await onReReviewChangeSet(changeSetId)
    } catch (caughtError) {
      setFileActionError(
        caughtError instanceof Error ? caughtError.message : '重新代码审查失败',
      )
    }
  }

  useEffect(() => {
    if (!previewFilePath) {
      return
    }

    const currentFile = files.find((file) => file.path === previewFilePath)
    if (!currentFile) {
      setPreviewFile(null)
      return
    }

    let ignore = false
    const refreshOpenFile = async () => {
      try {
        const nextPreviewFile = await onPreviewFileRef.current(currentFile)
        if (!ignore) {
          setPreviewFile(nextPreviewFile)
          setFileActionError(null)
        }
      } catch (caughtError) {
        if (!ignore) {
          setFileActionError(
            caughtError instanceof Error ? caughtError.message : '读取文件失败',
          )
        }
      }
    }

    void refreshOpenFile()

    return () => {
      ignore = true
    }
  }, [files, previewFilePath, workspaceRefreshToken])

  return (
    <section className="workspace-panel">
      <header className="panel-header">
        <p className="eyebrow">Workspace</p>
        <h2>预览与变更</h2>
      </header>

      <div className="preview-card workspace-status-card">
        <div className="workspace-status-info">
          <span className="preview-label">正式 Workspace</span>
          <strong title={workspaceId}>{workspaceId}</strong>
        </div>
        <Badge
          className={`status-pill status-${previewStatus}`}
          status={getPreviewBadgeStatus(preview?.status)}
          text={previewStatusLabel}
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
          onClick={() =>
            workspacePreviewUrl
              ? window.open(workspacePreviewUrl, '_blank', 'noopener,noreferrer')
              : undefined
          }
          size="small"
        >
          打开预览
        </Button>
      </div>

      <section className="workspace-section workspace-candidate-section">
        <div className="workspace-section-title">
          <EyeOutlined />
          <h3>候选 Preview</h3>
          <Tag>{candidateChangeSets.length}</Tag>
        </div>
        {candidateChangeSets.length > 0 ? (
          <div className="candidate-preview-list">
            {candidateChangeSets.map((candidate) => (
              <div className="candidate-preview-card" key={candidate.id}>
                <div className="workspace-preview-action">
                  <span>
                    {candidate.id} · {getChangeSetStatusLabel(candidate.status)}
                  </span>
                  <Button
                    disabled={!candidate.entry_path}
                    icon={<EyeOutlined />}
                    onClick={() => setPreviewingCandidateId(candidate.id)}
                    size="small"
                  >
                    打开隔离预览
                  </Button>
                  {candidate.status === 'failed' &&
                  hasCompleteCandidateSnapshot(candidate) ? (
                    <Button
                      loading={reReviewingChangeSetId === candidate.id}
                      onClick={() => void handleReReviewChangeSet(candidate.id)}
                      size="small"
                    >
                      重新代码审查
                    </Button>
                  ) : null}
                  {candidate.status === 'ready' ? (
                    <Button
                      loading={promotingChangeSetId === candidate.id}
                      onClick={() => void handlePromoteChangeSet(candidate.id)}
                      size="small"
                      type="primary"
                    >
                      合入 Workspace
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            className="empty-artifacts"
            description="当前没有候选 Change Set。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
      </section>

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
            {appliedDiffGroups.map((group) => {
              const reverted = group.records.every((record) => record.reverted_at)
              const firstRecord = group.records[0]
              return (
              <article className="workspace-change-row" key={group.id}>
                <div className="workspace-change-summary">
                  <div>
                    <strong>
                      {group.changeSetId
                        ? `Change Set ${group.changeSetId.replace('changeset_', '').slice(0, 10)}`
                        : firstRecord.path ?? firstRecord.artifact_id}
                    </strong>
                    <span>
                      <ClockCircleOutlined /> {formatTime(firstRecord.applied_at)}
                    </span>
                  </div>
                  <div className="workspace-change-actions">
                    <Tag>{group.records.length} 个文件</Tag>
                  {reverted && group.changeSetId ? (
                    <Button
                      loading={reapplyingChangeSetId === group.changeSetId}
                      onClick={() => void handleReapplyChangeSet(group.changeSetId!)}
                      size="small"
                      type="primary"
                    >
                      重新应用
                    </Button>
                  ) : group.changeSetId ? (
                    <Popconfirm
                      cancelText="取消"
                      description={`将一次性恢复 ${group.records.length} 个文件，不会留下部分回退状态。`}
                      okText="整组回退"
                      onConfirm={() => void handleRevertChangeSet(group.changeSetId!)}
                      title="回退整个 Change Set？"
                    >
                      <Button
                        icon={<RollbackOutlined />}
                        loading={revertingDiffRecordId === group.changeSetId}
                        size="small"
                      >
                        整组回退
                      </Button>
                    </Popconfirm>
                  ) : reverted ? (
                    <Tag>已回退</Tag>
                  ) : (
                    <Popconfirm
                      cancelText="取消"
                      description={`回退后 ${firstRecord.path ?? firstRecord.artifact_id} 会恢复到应用前的内容。`}
                      okText="回退"
                      onConfirm={() => void handleRevertAppliedDiff(firstRecord)}
                      title="回退这条旧变更？"
                    >
                      <Button
                        icon={<RollbackOutlined />}
                        loading={revertingDiffRecordId === firstRecord.id}
                        size="small"
                      >
                        回退
                      </Button>
                    </Popconfirm>
                  )}
                  </div>
                </div>
                {group.records.map((diff) => (
                  <details className="workspace-change-file" key={diff.id} open={group.records.length === 1}>
                    <summary>
                      <span>{diff.path ?? diff.artifact_id}</span>
                      <Tag>{getDiffSummary(diff.diff)}</Tag>
                    </summary>
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
                  </details>
                ))}
              </article>
              )
            })}
          </div>
        )}
      </section>
      <Modal
        centered
        className="workspace-preview-modal candidate-preview-modal"
        footer={[
          <Button key="close" onClick={() => setPreviewingCandidateId(null)}>
            关闭
          </Button>,
          <Button
            disabled={!candidatePreviewUrl}
            icon={<ExportOutlined />}
            key="new-window"
            onClick={() =>
              candidatePreviewUrl
                ? window.open(candidatePreviewUrl, '_blank', 'noopener,noreferrer')
                : undefined
            }
            type="primary"
          >
            新窗口打开
          </Button>,
        ]}
        onCancel={() => setPreviewingCandidateId(null)}
        open={Boolean(previewingCandidate)}
        title={
          <div className="candidate-preview-modal-title">
            <span>候选隔离预览</span>
            {previewingCandidate ? (
              <Tag>{getChangeSetStatusLabel(previewingCandidate.status)}</Tag>
            ) : null}
          </div>
        }
        width={WORKSPACE_PREVIEW_MODAL_WIDTH}
      >
        {candidatePreviewUrl ? (
          <iframe
            className="candidate-live-preview-frame"
            sandbox="allow-scripts allow-forms allow-same-origin allow-modals"
            src={candidatePreviewUrl}
            title={`${previewingCandidateId ?? '候选页面'} 人工隔离预览`}
          />
        ) : (
          <Empty description="当前候选没有可预览的 HTML 入口。" />
        )}
      </Modal>
      <Modal
        centered
        className="workspace-preview-modal workspace-file-preview-modal"
        footer={null}
        onCancel={() => setPreviewFile(null)}
        open={previewFile !== null}
        title={previewFile?.path}
        width={WORKSPACE_PREVIEW_MODAL_WIDTH}
      >
        {previewFile
          ? renderFilePreview(previewFile, getFilePreviewUrl(previewFile.path))
          : null}
      </Modal>
    </section>
  )
}

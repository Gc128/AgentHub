import { useState } from 'react'
import {
  CheckCircleOutlined,
  CopyOutlined,
  EyeOutlined,
  FileTextOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { Button, Tag } from 'antd'
import type { Artifact, ChangeSet } from '../../types/api'
import {
  getArtifactNumber,
  getArtifactString,
  getArtifactStringList,
} from '../artifactCards/artifactData'
import { parseDiffLines } from '../artifactCards/diffLines'

type MessageArtifactActionsProps = {
  /** 当前消息携带的结构化产物。 */
  artifacts: Artifact[]
  /** 后端实时 Change Set 状态，不信任历史 artifact 中的状态。 */
  changeSets: ChangeSet[]
  promotingChangeSetId: string | null
  getCandidatePreviewUrl: (changeSetId: string, path?: string) => string
  getWorkspacePreviewUrl: (path?: string) => string
  onPromoteChangeSet: (changeSetId: string) => Promise<void>
}

const getArtifactLabel = (artifact: Artifact) => {
  if (artifact.type === 'diff' || artifact.type === 'code') {
    return getArtifactString(artifact, 'filename', artifact.title)
  }
  if (artifact.type === 'preview') {
    return getArtifactString(artifact, 'change_set_id', artifact.title)
  }
  const summary = getArtifactString(artifact, 'summary')
  return summary || artifact.title
}

type CandidateOperation = {
  path: string
  operation: 'upsert' | 'delete'
}

const isCandidateManifest = (artifact: Artifact) =>
  artifact.type === 'file' &&
  (getArtifactString(artifact, 'kind') === 'candidate_manifest' ||
    artifact.id === 'artifact-code-agent-candidate-manifest' ||
    artifact.title === 'Candidate manifest')

const getCandidateOperations = (artifact: Artifact): CandidateOperation[] => {
  const operations = artifact.data.operations
  if (!Array.isArray(operations)) {
    return []
  }
  return operations.flatMap((operation) => {
    if (
      typeof operation !== 'object' ||
      operation === null ||
      !('path' in operation) ||
      typeof operation.path !== 'string'
    ) {
      return []
    }
    return [
      {
        path: operation.path,
        operation:
          'operation' in operation && operation.operation === 'delete'
            ? 'delete'
            : 'upsert',
      } satisfies CandidateOperation,
    ]
  })
}

const getChangeSetStatusLabel = (status: string) =>
  ({
    conflicted: '冲突',
    fail: '失败',
    failed: '审查失败',
    generated: '已生成',
    needs_fix: '待修复',
    not_started: '未开始',
    pass: '通过',
    promoted: '已合入',
    promoting: '合入中',
    ready: '可合入',
    rejected: '已拒绝',
    staging: '隔离准备中',
    validating: '审查中',
  })[status] ?? status

const getReviewVerdictLabel = (verdict: string) =>
  ({ fail: '失败', pass: '通过', pass_with_warnings: '通过（有警告）' })[
    verdict
  ] ?? verdict

const getRiskLabel = (riskLevel: string) =>
  ({ high: '高风险', low: '低风险', medium: '中风险' })[riskLevel] ?? riskLevel

/**
 * 聊天流内的轻量 artifact 操作条。
 * 完整内容由 Markdown 主回复承载，这里只保留可执行动作。
 */
export function MessageArtifactActions({
  artifacts,
  changeSets,
  promotingChangeSetId,
  getCandidatePreviewUrl,
  getWorkspacePreviewUrl,
  onPromoteChangeSet,
}: MessageArtifactActionsProps) {
  const [expandedArtifactIds, setExpandedArtifactIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )

  if (artifacts.length === 0) {
    return null
  }

  return (
    <div className="message-artifact-actions">
      {artifacts.map((artifact) => {
        const label = getArtifactLabel(artifact)

        if (isCandidateManifest(artifact)) {
          const operations = getCandidateOperations(artifact)
          const fileCount = getArtifactNumber(artifact, 'file_count') ?? operations.length
          return (
            <div className="candidate-manifest-card" key={artifact.id}>
              <div className="message-artifact-action">
                <Tag className="artifact-type">file</Tag>
                <FileTextOutlined />
                <span>候选文件清单</span>
                <Tag>{fileCount} 个候选文件</Tag>
              </div>
              {operations.length > 0 ? (
                <ul className="candidate-manifest-files">
                  {operations.map((operation) => (
                    <li key={`${operation.operation}-${operation.path}`}>
                      <Tag color={operation.operation === 'delete' ? 'error' : 'processing'}>
                        {operation.operation === 'delete' ? '删除' : '写入'}
                      </Tag>
                      <code>{operation.path}</code>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )
        }

        if (artifact.type === 'diff') {
          const diff = getArtifactString(artifact, 'diff')
          const diffLines = parseDiffLines(diff)
          return (
            <div className="message-artifact-diff-card" key={artifact.id}>
              <div className="message-artifact-action">
                <Tag className="artifact-type">{artifact.type}</Tag>
                <span>{label}</span>
                <Tag>候选变更（只读）</Tag>
              </div>
              {diff ? (
                <div className="diff-viewer message-diff-viewer">
                  {diffLines.map((line, index) => (
                    <pre
                      className={`diff-line diff-line-${line.kind}`}
                      key={`${index}-${line.content}`}
                    >
                      {line.content || ' '}
                    </pre>
                  ))}
                </div>
              ) : null}
            </div>
          )
        }

        if (artifact.type === 'code') {
          const code = getArtifactString(artifact, 'content')
          return (
            <div className="message-artifact-action" key={artifact.id}>
              <Tag className="artifact-type">{artifact.type}</Tag>
              <span>{label}</span>
              <Button
                disabled={!code}
                icon={<CopyOutlined />}
                onClick={() => navigator.clipboard.writeText(code)}
                size="small"
              >
                复制代码
              </Button>
            </div>
          )
        }

        if (artifact.type === 'preview') {
          const changeSetId = getArtifactString(artifact, 'change_set_id')
          const changeSet = changeSets.find((item) => item.id === changeSetId)
          const scope = getArtifactString(artifact, 'scope', 'candidate')
          const entryPath =
            changeSet?.entry_path ?? getArtifactString(artifact, 'entry_path')
          const previewUrl = scope === 'candidate' && changeSetId
            ? getCandidatePreviewUrl(
                changeSetId,
                entryPath,
              )
            : getWorkspacePreviewUrl(entryPath)
          return (
            <div className="message-artifact-action" key={artifact.id}>
              <Tag className="artifact-type">{artifact.type}</Tag>
              <span>{label}</span>
              <Tag>人工预览</Tag>
              <Button
                disabled={!previewUrl}
                icon={<EyeOutlined />}
                onClick={() => window.open(previewUrl, '_blank', 'noopener,noreferrer')}
                size="small"
              >
                打开预览
              </Button>
            </div>
          )
        }

        if (artifact.type === 'change_set') {
          const changeSetId = getArtifactString(artifact, 'change_set_id')
          const changeSet = changeSets.find((item) => item.id === changeSetId)
          const status = changeSet?.status ?? getArtifactString(artifact, 'status', 'generated')
          const promoting = promotingChangeSetId === changeSetId
          const canPromote = status === 'ready'
          const reviewReport = changeSet?.review_report
          const promoteLabel =
            status === 'ready'
              ? '合入 Workspace'
              : status === 'promoted'
                ? '已合入'
                : ['failed', 'rejected', 'conflicted'].includes(status)
                  ? '不可合入'
                  : '等待审查'
          return (
            <div className="message-artifact-file-card" key={artifact.id}>
              <div className="message-artifact-action">
                <Tag className="artifact-type">change set</Tag>
                <span>{changeSetId || label}</span>
                <Tag>{getChangeSetStatusLabel(status)}</Tag>
                {changeSetId && changeSet?.entry_path ? (
                  <Button
                    icon={<EyeOutlined />}
                    onClick={() =>
                      window.open(
                        getCandidatePreviewUrl(changeSetId, changeSet.entry_path ?? undefined),
                        '_blank',
                        'noopener,noreferrer',
                      )
                    }
                    size="small"
                  >
                    候选预览
                  </Button>
                ) : null}
                <Button
                  disabled={!canPromote || !changeSetId || promoting}
                  icon={promoting ? <LoadingOutlined /> : <CheckCircleOutlined />}
                  loading={promoting}
                  onClick={() => void onPromoteChangeSet(changeSetId)}
                  size="small"
                  type="primary"
                >
                  {promoteLabel}
                </Button>
              </div>
              {reviewReport ? (
                <div className="change-set-validation-summary">
                  <section>
                    <div className="change-set-validation-heading">
                      <strong>代码审查</strong>
                      <Tag color={reviewReport.verdict === 'fail' ? 'error' : 'success'}>
                        {getReviewVerdictLabel(reviewReport.verdict)}
                      </Tag>
                      <Tag>{getRiskLabel(reviewReport.risk_level)}</Tag>
                    </div>
                    <p>{reviewReport.summary}</p>
                    {reviewReport.findings.length > 0 ? (
                      <ul>
                        {reviewReport.findings.map((finding, index) => (
                          <li key={`${finding.category}-${index}`}>
                            <strong>{finding.category}：</strong>
                            {finding.message}
                            {finding.path ? <code> ({finding.path})</code> : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </section>
                </div>
              ) : null}
            </div>
          )
        }

        const findings = getArtifactStringList(artifact, 'findings')
        const expanded = expandedArtifactIds.has(artifact.id)
        return (
          <div className="message-artifact-file-card" key={artifact.id}>
            <div className="message-artifact-action">
              <Tag className="artifact-type">{artifact.type}</Tag>
              <FileTextOutlined />
              <span>{findings[0] ?? label}</span>
              <Button
                icon={<EyeOutlined />}
                onClick={() =>
                  setExpandedArtifactIds((currentIds) => {
                    const nextIds = new Set(currentIds)
                    if (nextIds.has(artifact.id)) {
                      nextIds.delete(artifact.id)
                    } else {
                      nextIds.add(artifact.id)
                    }
                    return nextIds
                  })
                }
                size="small"
              >
                {expanded ? '收起' : '查看详情'}
              </Button>
            </div>
            {expanded ? (
              <pre className="message-artifact-json">
                {JSON.stringify(artifact.data, null, 2)}
              </pre>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

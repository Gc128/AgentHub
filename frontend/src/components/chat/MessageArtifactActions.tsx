import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  EyeOutlined,
  FileTextOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { Button, Tag } from 'antd'
import type { Artifact } from '../../types/api'
import { getArtifactString, getArtifactStringList } from '../artifactCards/artifactData'

type MessageArtifactActionsProps = {
  /** 当前消息携带的结构化产物。 */
  artifacts: Artifact[]
  /** 已应用 Diff 的 artifact id 集合。 */
  appliedDiffIds: ReadonlySet<string>
  /** 当前正在应用的 Diff artifact id。 */
  applyingDiffId: string | null
  /** 点击 Apply Diff 时由父组件调用后端接口。 */
  onApplyDiff: (artifact: Artifact, diff: string) => Promise<void>
}

const getArtifactLabel = (artifact: Artifact) => {
  if (artifact.type === 'diff' || artifact.type === 'code') {
    return getArtifactString(artifact, 'filename', artifact.title)
  }
  if (artifact.type === 'preview') {
    return getArtifactString(artifact, 'workspace_id', artifact.title)
  }
  const summary = getArtifactString(artifact, 'summary')
  return summary || artifact.title
}

/**
 * 聊天流内的轻量 artifact 操作条。
 * 完整内容由 Markdown 主回复承载，这里只保留可执行动作。
 */
export function MessageArtifactActions({
  artifacts,
  appliedDiffIds,
  applyingDiffId,
  onApplyDiff,
}: MessageArtifactActionsProps) {
  if (artifacts.length === 0) {
    return null
  }

  return (
    <div className="message-artifact-actions">
      {artifacts.map((artifact) => {
        const label = getArtifactLabel(artifact)

        if (artifact.type === 'diff') {
          const diff = getArtifactString(artifact, 'diff')
          const applied = appliedDiffIds.has(artifact.id)
          const applying = applyingDiffId === artifact.id
          return (
            <div className="message-artifact-action" key={artifact.id}>
              <Tag className="artifact-type">{artifact.type}</Tag>
              <span>{label}</span>
              <Button
                disabled={applied || applying || !diff}
                icon={
                  applied ? (
                    <CheckCircleOutlined />
                  ) : applying ? (
                    <LoadingOutlined />
                  ) : (
                    <CloudUploadOutlined />
                  )
                }
                loading={applying}
                onClick={() => onApplyDiff(artifact, diff)}
                size="small"
              >
                {applied ? '已应用' : 'Apply Diff'}
              </Button>
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
          const previewUrl = getArtifactString(artifact, 'preview_url')
          const status = getArtifactString(artifact, 'status', 'not_started')
          return (
            <div className="message-artifact-action" key={artifact.id}>
              <Tag className="artifact-type">{artifact.type}</Tag>
              <span>{label}</span>
              <Tag>{status}</Tag>
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

        const findings = getArtifactStringList(artifact, 'findings')
        return (
          <div className="message-artifact-action" key={artifact.id}>
            <Tag className="artifact-type">{artifact.type}</Tag>
            <FileTextOutlined />
            <span>{findings[0] ?? label}</span>
          </div>
        )
      })}
    </div>
  )
}

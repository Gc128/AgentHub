import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { Alert, Button, Tag } from 'antd'
import { useState } from 'react'
import type { Artifact } from '../../types/api'
import { getArtifactString } from './artifactData'
import { parseDiffLines } from './diffLines'

type DiffArtifactCardProps = {
  /** diff 类型的 Artifact，data 中应包含 filename/diff。 */
  artifact: Artifact
  /** 当前 diff 是否已经应用；父组件用 artifact.id 统一管理状态。 */
  applied: boolean
  /** 当前 diff 是否正在应用；用于禁用按钮和展示进行中状态。 */
  applying: boolean
  /** 点击 Apply Diff 时调用，父组件负责请求后端 API 并刷新 Preview。 */
  onApplyDiff?: (artifact: Artifact, diff: string) => Promise<void>
}

/**
 * Diff 产物卡片。
 * 负责把 unified diff 按新增/删除/上下文分色展示，方便 Demo 时解释代码变更。
 */
export function DiffArtifactCard({
  artifact,
  applied,
  applying,
  onApplyDiff,
}: DiffArtifactCardProps) {
  // applyError 是卡片局部错误，只用于告诉用户这一次点击为什么失败。
  const [applyError, setApplyError] = useState<string | null>(null)
  const filename = getArtifactString(artifact, 'filename', '未命名文件')
  const diff = getArtifactString(artifact, 'diff', '')
  const diffLines = parseDiffLines(diff)
  const canApply = Boolean(onApplyDiff) && !applied && !applying

  /** 点击应用 Diff；成功后状态由父组件 appliedDiffIds 统一刷新。 */
  const handleApplyDiff = async () => {
    if (!onApplyDiff) {
      return
    }

    setApplyError(null)

    try {
      await onApplyDiff(artifact, diff)
    } catch (caughtError) {
      setApplyError(
        caughtError instanceof Error ? caughtError.message : '应用 Diff 失败',
      )
    }
  }

  return (
    <article className="artifact-card artifact-card-diff">
      <header className="artifact-card-top">
        <div>
          {/* diff 类型继续来自后端 Artifact.type，不新增前端私有字段。 */}
          <Tag className="artifact-type">{artifact.type}</Tag>
          <h3>{artifact.title}</h3>
        </div>
        <div className="artifact-actions">
          <span className="artifact-file-name">{filename}</span>
          <Button
            className={applied ? 'artifact-action is-applied' : 'artifact-action'}
            disabled={!canApply}
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
            onClick={handleApplyDiff}
            size="small"
          >
            {applied ? '已应用' : applying ? '应用中...' : 'Apply Diff'}
          </Button>
        </div>
      </header>
      <div className="diff-viewer" aria-label={`${filename} diff`}>
        {diffLines.map((line, index) => (
          <pre
            className={`diff-line diff-line-${line.kind}`}
            key={`${index}-${line.content}`}
          >
            {line.content || ' '}
          </pre>
        ))}
      </div>
      {applyError ? (
        <Alert
          className="form-error"
          showIcon
          title={applyError}
          type="error"
        />
      ) : null}
    </article>
  )
}

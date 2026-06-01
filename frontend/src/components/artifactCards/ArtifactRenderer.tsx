import type { Artifact } from '../../types/api'
import { CodeArtifactCard } from './CodeArtifactCard'
import { DiffArtifactCard } from './DiffArtifactCard'
import { GenericArtifactCard } from './GenericArtifactCard'
import { PreviewArtifactCard } from './PreviewArtifactCard'

type ArtifactRendererProps = {
  /** 需要渲染的结构化产物。 */
  artifact: Artifact
  /** 已经成功应用的 diff artifact ID 集合。 */
  appliedDiffIds: ReadonlySet<string>
  /** 当前正在应用的 diff artifact ID。 */
  applyingDiffId: string | null
  /** 点击 Apply Diff 时调用；只有 diff 卡片会使用。 */
  onApplyDiff?: (artifact: Artifact, diff: string) => Promise<void>
}

/**
 * Artifact 类型分发器。
 * 组件只根据 artifact.type 选择卡片，不在业务层硬编码 data 字段，方便后续扩展 deploy/file 等产物。
 */
export function ArtifactRenderer({
  artifact,
  appliedDiffIds,
  applyingDiffId,
  onApplyDiff,
}: ArtifactRendererProps) {
  if (artifact.type === 'code') {
    return <CodeArtifactCard artifact={artifact} />
  }

  if (artifact.type === 'diff') {
    return (
      <DiffArtifactCard
        applied={appliedDiffIds.has(artifact.id)}
        applying={applyingDiffId === artifact.id}
        artifact={artifact}
        onApplyDiff={onApplyDiff}
      />
    )
  }

  if (artifact.type === 'preview') {
    return <PreviewArtifactCard artifact={artifact} />
  }

  return <GenericArtifactCard artifact={artifact} />
}

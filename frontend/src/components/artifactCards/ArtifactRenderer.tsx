import type { Artifact } from '../../types/api'
import { CodeArtifactCard } from './CodeArtifactCard'
import { DiffArtifactCard } from './DiffArtifactCard'
import { GenericArtifactCard } from './GenericArtifactCard'
import { PreviewArtifactCard } from './PreviewArtifactCard'

type ArtifactRendererProps = {
  /** 需要渲染的结构化产物。 */
  artifact: Artifact
}

/**
 * Artifact 类型分发器。
 * 组件只根据 artifact.type 选择卡片，不在业务层硬编码 data 字段，方便后续扩展 deploy/file 等产物。
 */
export function ArtifactRenderer({ artifact }: ArtifactRendererProps) {
  if (artifact.type === 'code') {
    return <CodeArtifactCard artifact={artifact} />
  }

  if (artifact.type === 'diff') {
    return <DiffArtifactCard artifact={artifact} />
  }

  if (artifact.type === 'preview') {
    return <PreviewArtifactCard artifact={artifact} />
  }

  return <GenericArtifactCard artifact={artifact} />
}

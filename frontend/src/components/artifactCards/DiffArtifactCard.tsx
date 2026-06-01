import type { Artifact } from '../../types/api'
import { getArtifactString } from './artifactData'

type DiffArtifactCardProps = {
  /** diff 类型的 Artifact，data 中应包含 filename/diff。 */
  artifact: Artifact
}

type DiffLine = {
  /** 原始 diff 行文本。 */
  content: string
  /** 行类型，用于决定新增、删除、文件头和上下文样式。 */
  kind: 'added' | 'removed' | 'meta' | 'context'
}

/** 根据 unified diff 行前缀判断行类型。 */
const getDiffLineKind = (line: string): DiffLine['kind'] => {
  if (
    line.startsWith('+++') ||
    line.startsWith('---') ||
    line.startsWith('@@')
  ) {
    return 'meta'
  }
  if (line.startsWith('+')) {
    return 'added'
  }
  if (line.startsWith('-')) {
    return 'removed'
  }
  return 'context'
}

/**
 * 把 unified diff 字符串拆成可渲染的行模型。
 * 这里不尝试完整解析 diff 语法，只做前端展示需要的轻量分类。
 */
const parseDiffLines = (diff: string): DiffLine[] =>
  diff.split('\n').map((line) => ({
    content: line,
    kind: getDiffLineKind(line),
  }))

/**
 * Diff 产物卡片。
 * 负责把 unified diff 按新增/删除/上下文分色展示，方便 Demo 时解释代码变更。
 */
export function DiffArtifactCard({ artifact }: DiffArtifactCardProps) {
  const filename = getArtifactString(artifact, 'filename', '未命名文件')
  const diff = getArtifactString(artifact, 'diff', '')
  const diffLines = parseDiffLines(diff)

  return (
    <article className="artifact-card artifact-card-diff">
      <header className="artifact-card-top">
        <div>
          <span className="artifact-type">{artifact.type}</span>
          <h3>{artifact.title}</h3>
        </div>
        <span className="artifact-file-name">{filename}</span>
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
    </article>
  )
}

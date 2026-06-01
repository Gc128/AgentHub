import type { Artifact } from '../../types/api'
import { getArtifactNumber, getArtifactStringList } from './artifactData'

type GenericArtifactCardProps = {
  /** file/deploy 或未知类型 Artifact，用通用结构展示 data。 */
  artifact: Artifact
}

/**
 * 通用 Artifact 卡片。
 * Orchestrator 的任务拆解和 Review notes 当前都使用 file artifact，因此需要一个不丢信息的兜底渲染器。
 */
export function GenericArtifactCard({ artifact }: GenericArtifactCardProps) {
  const steps = getArtifactStringList(artifact, 'steps')
  const findings = getArtifactStringList(artifact, 'findings')
  const estimatedMinutes = getArtifactNumber(artifact, 'estimated_minutes')
  const listItems = steps.length > 0 ? steps : findings

  return (
    <article className="artifact-card artifact-card-generic">
      <header className="artifact-card-top">
        <div>
          <span className="artifact-type">{artifact.type}</span>
          <h3>{artifact.title}</h3>
        </div>
        {estimatedMinutes ? (
          <span className="artifact-file-name">{estimatedMinutes} min</span>
        ) : null}
      </header>
      {listItems.length > 0 ? (
        <ol className="artifact-list-content">
          {listItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      ) : (
        <pre className="artifact-json-block">
          {JSON.stringify(artifact.data, null, 2)}
        </pre>
      )}
    </article>
  )
}

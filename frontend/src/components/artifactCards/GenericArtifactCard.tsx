import { ClockCircleOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import type { Artifact } from '../../types/api'
import { getArtifactNumber, getArtifactStringList } from './artifactData'

type GenericArtifactCardProps = {
  /** file/deploy 或未知类型 Artifact，用通用结构展示 data。 */
  artifact: Artifact
}

/**
 * 通用 Artifact 卡片。
 * Review notes、harness report 和未知 artifact 使用这里兜底展示，避免丢失结构化信息。
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
          {/* file/deploy 等非 P0 专用产物用通用 Tag 标出类型。 */}
          <Tag className="artifact-type">{artifact.type}</Tag>
          <h3>{artifact.title}</h3>
        </div>
        {estimatedMinutes ? (
          <Tag className="artifact-file-name" icon={<ClockCircleOutlined />}>
            {estimatedMinutes} min
          </Tag>
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

import {
  CheckOutlined,
  CloseCircleOutlined,
  CopyOutlined,
} from '@ant-design/icons'
import { Button, Tag } from 'antd'
import { useState } from 'react'
import type { Artifact } from '../../types/api'
import { getArtifactString } from './artifactData'

type CodeArtifactCardProps = {
  /** code 类型的 Artifact，data 中应包含 filename/language/content。 */
  artifact: Artifact
}

/**
 * 代码产物卡片。
 * 负责展示文件名、语言和代码内容，并提供复制按钮，满足 Demo 中“代码不要只放自然语言里”的要求。
 */
export function CodeArtifactCard({ artifact }: CodeArtifactCardProps) {
  // copyState 只影响当前按钮文案，不进入全局状态，避免组件之间互相干扰。
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>(
    'idle',
  )
  const filename = getArtifactString(artifact, 'filename', '未命名文件')
  const language = getArtifactString(artifact, 'language', 'text')
  const content = getArtifactString(artifact, 'content', '// 暂无代码内容')

  /** 复制代码到剪贴板；浏览器不支持时给出失败状态。 */
  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 1600)
    } catch {
      setCopyState('failed')
      window.setTimeout(() => setCopyState('idle'), 1600)
    }
  }

  return (
    <article className="artifact-card artifact-card-code">
      <header className="artifact-card-top">
        <div>
          {/* 产物类型使用 Tag 展示，视觉上和 Agent 能力标签保持一致。 */}
          <Tag className="artifact-type">{artifact.type}</Tag>
          <h3>{artifact.title}</h3>
        </div>
        <Button
          className="artifact-action"
          icon={
            copyState === 'copied' ? (
              <CheckOutlined />
            ) : copyState === 'failed' ? (
              <CloseCircleOutlined />
            ) : (
              <CopyOutlined />
            )
          }
          onClick={handleCopyCode}
          size="small"
        >
          {copyState === 'copied'
            ? '已复制'
            : copyState === 'failed'
              ? '复制失败'
              : '复制代码'}
        </Button>
      </header>
      <div className="artifact-meta-row">
        <span>{filename}</span>
        <span>{language}</span>
      </div>
      <pre className="code-block">
        <code>{content}</code>
      </pre>
    </article>
  )
}

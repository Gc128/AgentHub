import { CopyOutlined, EyeOutlined } from '@ant-design/icons'
import { Button, Modal, Tooltip } from 'antd'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

type MarkdownMessageProps = {
  /** 后端 Agent 返回的 Markdown 主回复。 */
  content: string
}

type CodeElementNode = {
  data?: {
    meta?: string | null
  }
}

type CodeRendererProps = {
  children?: React.ReactNode
  className?: string
  node?: CodeElementNode
}

const markdownSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [
      ...(defaultSchema.attributes?.code ?? []),
      ['className', /^language-[\w-]+$/],
    ],
  },
}

const getCodeFilename = (meta: string | undefined) => {
  if (!meta) {
    return null
  }

  const match = meta.match(/(?:^|\s)file=([^\s]+)/)
  return match?.[1] ?? null
}

/**
 * Markdown 消息渲染器。
 * 用 Markdown 承载 Agent 的自然回复，用结构化 artifacts 承载可执行动作。
 */
export function MarkdownMessage({ content }: MarkdownMessageProps) {
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)

  const renderCode = ({ children, className, node }: CodeRendererProps) => {
    const rawCode = String(children ?? '').replace(/\n$/, '')
    const languageMatch = /language-([\w-]+)/.exec(className ?? '')
    const language = languageMatch?.[1] ?? null
    const filename = getCodeFilename(node?.data?.meta ?? undefined)

    if (!language) {
      return <code className="markdown-inline-code">{children}</code>
    }

    const canPreviewHtml = language.toLowerCase() === 'html'

    return (
      <div className="markdown-code-shell">
        <div className="markdown-code-toolbar">
          <div className="markdown-code-meta">
            <span>{language}</span>
            {filename ? <strong>{filename}</strong> : null}
          </div>
          <div className="markdown-code-actions">
            {canPreviewHtml ? (
              <Tooltip title="在安全 iframe 中预览 HTML">
                <Button
                  icon={<EyeOutlined />}
                  onClick={() => setPreviewHtml(rawCode)}
                  size="small"
                  type="text"
                >
                  预览
                </Button>
              </Tooltip>
            ) : null}
            <Tooltip title="复制代码">
              <Button
                icon={<CopyOutlined />}
                onClick={() => navigator.clipboard.writeText(rawCode)}
                size="small"
                type="text"
              >
                复制
              </Button>
            </Tooltip>
          </div>
        </div>
        <SyntaxHighlighter
          customStyle={{ background: 'transparent', margin: 0, padding: 0 }}
          language={language}
          PreTag="div"
          showLineNumbers={rawCode.split('\n').length > 8}
          style={oneLight}
          wrapLongLines
        >
          {rawCode}
        </SyntaxHighlighter>
      </div>
    )
  }

  return (
    <>
      <div className="markdown-message">
        <ReactMarkdown
          components={{
            code: renderCode,
          }}
          rehypePlugins={[[rehypeSanitize, markdownSanitizeSchema]]}
          remarkPlugins={[remarkGfm]}
        >
          {content}
        </ReactMarkdown>
      </div>
      <Modal
        footer={null}
        onCancel={() => setPreviewHtml(null)}
        open={previewHtml !== null}
        title="HTML 预览"
        width={880}
      >
        <iframe
          className="markdown-html-preview"
          sandbox=""
          srcDoc={previewHtml ?? ''}
          title="HTML code preview"
        />
      </Modal>
    </>
  )
}

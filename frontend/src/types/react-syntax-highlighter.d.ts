declare module 'react-syntax-highlighter' {
  import type { ComponentType, ReactNode } from 'react'

  export type SyntaxHighlighterProps = {
    children?: ReactNode
    className?: string
    customStyle?: Record<string, string | number>
    language?: string
    PreTag?: string
    showLineNumbers?: boolean
    style?: Record<string, unknown>
    wrapLongLines?: boolean
  }

  export const Prism: ComponentType<SyntaxHighlighterProps>
}

declare module 'react-syntax-highlighter/dist/esm/styles/prism' {
  export const oneLight: Record<string, unknown>
}

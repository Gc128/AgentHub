import type { ReactNode } from 'react'

/**
 * 应用三栏布局的插槽参数。
 * sidebar 放会话和 Agent；main 放聊天主流程；aside 放 Artifact 和 Preview。
 */
type AppLayoutProps = {
  /** 左侧栏内容，当前包含品牌、会话列表和 Agent 列表。 */
  sidebar: ReactNode
  /** 中间主内容，当前是聊天头、消息流和输入区占位。 */
  main: ReactNode
  /** 右侧栏内容，当前是 workspace preview 和 artifacts 聚合列表。 */
  aside: ReactNode
}

/**
 * AgentHub 桌面端基础布局。
 * 这里只负责结构插槽，不关心数据来源，方便后续替换或扩展各区域组件。
 */
export function AppLayout({ sidebar, main, aside }: AppLayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">{sidebar}</aside>
      <main className="chat-area">{main}</main>
      <aside className="artifact-area">{aside}</aside>
    </div>
  )
}

import type { ReactNode } from 'react'

/**
 * 应用三栏布局的插槽参数。
 * sidebar 放品牌、会话、Agent 图标区；main 放聊天；aside 放产物和预览。
 */
type AppLayoutProps = {
  /** 左侧栏完整内容 */
  sidebar: ReactNode
  /** 中间主内容：聊天头、消息流和输入区 */
  main: ReactNode
  /** 右侧栏内容：workspace preview 和 artifacts 列表 */
  aside: ReactNode
}

/**
 * AgentHub 桌面端基础三栏布局。
 * 只负责结构插槽，不关心数据来源。
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

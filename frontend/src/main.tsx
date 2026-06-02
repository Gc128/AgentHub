import { createRoot } from 'react-dom/client'
import 'antd/dist/reset.css'
import './index.css'
import App from './App.tsx'

// Ant Design reset 必须先于业务样式加载，确保组件库基础样式稳定，再交给 App.css 做产品定制。
createRoot(document.getElementById('root')!).render(
    <App />
)

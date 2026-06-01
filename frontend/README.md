# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default tseslint.config({
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

- Replace `tseslint.configs.recommended` to `tseslint.configs.recommendedTypeChecked` or `tseslint.configs.strictTypeChecked`
- Optionally add `...tseslint.configs.stylisticTypeChecked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and update the config:

```js
// eslint.config.js
import react from 'eslint-plugin-react'

export default tseslint.config({
  // Set the react version
  settings: { react: { version: '18.3' } },
  plugins: {
    // Add the react plugin
    react,
  },
  rules: {
    // other rules...
    // Enable its recommended rules
    ...react.configs.recommended.rules,
    ...react.configs['jsx-runtime'].rules,
  },
})
```

提示词：

我正在参加字节跳动 AI 全栈挑战赛，附件 1 是我们团队整理的需求文档，附件 2 是官方要求文档。我目前负责前端开发。

请你结合这两个文档和当前仓库代码，帮我完成前端任务拆解。请先阅读仓库结构、页面、组件、路由、API 请求封装和状态管理方式，再分析。

要求：

1. 理解项目核心需求和前端需要完成的功能。
2. 严格参考上传文档中的接口定义，不要随意创造字段。
3. 当前没有后端，请设计 mock 拦截请求和模拟数据。
4. 如果文档没有明确接口，但前端需要，请标注“文档未明确，建议补充”。
5. 如果仓库已有相关代码，请标注“已有基础，需要完善”；没有则标注“需要新建”。
6. 不要直接改代码，先只输出任务拆解。

请按以下格式输出：

1. 项目与仓库理解

简要说明项目目标、核心流程、当前前端技术栈和已有代码结构。

2. 前端模块拆分

按模块拆分功能，例如首页、Agent 管理、单聊、群聊、多 Agent 调度、会话历史、文件/知识库、设置等。每个模块说明：目标、涉及页面/组件、接口、是否需要 mock、优先级。

3. 开发任务清单

把任务拆成可逐个完成的小目标。每个任务包含：

* 任务编号
* 任务名称
* 需求描述
* 需要修改/新增的文件
* 依赖接口
* mock 数据要求
* 预期效果
* 验收标准
* 优先级 P0/P1/P2

4. 接口与 mock 方案

根据文档整理前端需要的 API，包括请求方法、路径、参数、返回结构和 mock 示例。

5. 一周开发顺序

给出适合前端单人推进的开发顺序，优先保证核心链路和可演示版本。
# LegalMind 前端

基于 **Vue 3 + Vite + Tailwind CSS** 构建的智能法律咨询系统前端。

## 技术栈

| 技术 | 用途 |
|------|------|
| Vue 3 (Composition API) | UI 框架 |
| Vite 8 | 构建工具 |
| Tailwind CSS 4 | 样式框架 |
| Pinia | 全局状态管理 |
| Vue Router 5 | 路由管理 |
| Axios | HTTP 客户端 |
| marked | Markdown 渲染 |

## 路由

| 路径 | 视图 | 说明 |
|------|------|------|
| `/` | Home | 首页/介绍页 |
| `/login` | Login | 登录 |
| `/register` | Register | 注册 |
| `/chat` | Chat | 法律咨询对话（支持 HITL 交互） |
| `/cases` | CaseSearch | 案例检索 |
| `/documents` | DocumentGenerate | 法律文书生成 |

## 状态管理（Pinia Stores）

- `auth.js` — 用户认证状态（token、用户信息、登录/注册/登出操作）
- `chat.js` — 聊天状态（会话列表、消息列表、实时消息流、`pendingInterrupt` 中断状态、`resumeInterrupt()` 恢复方法）

## 组件

```
src/
├── api/                 # Axios API 客户端
│   ├── client.js        # HTTP 客户端配置（拦截器、baseURL）
│   ├── chat.js          # 聊天 API（含 streamResumeMessage 恢复中断会话）
│   ├── documents.js     # 文书生成 API
│   └── cases.js         # 案例检索 API
├── components/
│   └── chat/
│       ├── ChatSidebar.vue   # 聊天会话侧边栏
│       ├── ChatMessage.vue   # 消息气泡（支持 Markdown 渲染）
│       ├── ChatInput.vue     # 消息输入框
│       └── InterruptCard.vue  # HITL 交互卡片（快捷选项 + 文本输入）
├── views/
│   ├── Login.vue              # 登录页
│   ├── Register.vue           # 注册页
│   ├── Chat.vue               # 聊天主页（集成 InterruptCard）
│   ├── CaseSearch.vue         # 案例检索页
│   └── DocumentGenerate.vue   # 文书生成页
├── stores/
│   ├── auth.js                # 认证状态
│   └── chat.js                # 聊天状态（含 interrupt 管理）
├── router/
│   └── index.js               # 路由配置
├── main.js                    # 应用入口
└── App.vue                    # 根组件
```

## HITL 交互流程

```
用户发消息 → /stream → 图执行 → interrupt 打破 → 前端收到 {interrupt} 事件
→ 渲染 InterruptCard → 用户回答 → /resume → 图恢复执行 → 正常输出
```

- `Chat.vue` 在收到 interrupt 事件时，用 `InterruptCard` 组件替换输入区
- `InterruptCard` 支持快捷选项点击和自定义文本输入
- 用户提交后调用 `streamResumeMessage()` 触发 `/api/chat/resume` 端点

## SSE 流式输出

- 聊天消息通过 SSE（Server-Sent Events）实时推送
- 流式输出时自动滚动到底部（监听消息条数 + 最后一条消息 content 长度）
- 首个 SSE 事件发送 `session_id`

## 开发

```bash
# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 预览生产构建
pnpm preview
```

## 后端 API 配置

API 基础 URL 在 `src/api/client.js` 中配置，默认指向 `http://localhost:8000`。

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
| `/chat` | Chat | 法律咨询对话 |
| `/cases` | CaseSearch | 案例检索 |
| `/documents` | DocumentGenerate | 法律文书生成 |

## 状态管理（Pinia Stores）

- `auth.js` — 用户认证状态（token、用户信息、登录/注册/登出操作）
- `chat.js` — 聊天状态（会话列表、消息列表、实时消息流）

## 组件

```
src/
├── api/                 # Axios API 客户端
│   ├── client.js        # HTTP 客户端配置（拦截器、baseURL）
│   ├── chat.js          # 聊天 API
│   ├── documents.js     # 文书生成 API
│   ├── cases.js         # 案例检索 API
│   └── auth.js          # 认证 API
├── components/
│   └── chat/
│       ├── ChatSidebar.vue   # 聊天会话侧边栏
│       ├── ChatMessage.vue   # 消息气泡（支持 Markdown 渲染）
│       └── ChatInput.vue     # 消息输入框
├── views/
│   ├── Login.vue              # 登录页
│   ├── Register.vue           # 注册页
│   ├── Chat.vue               # 聊天主页
│   ├── CaseSearch.vue         # 案例检索页
│   └── DocumentGenerate.vue   # 文书生成页
├── stores/
│   ├── auth.js                # 认证状态
│   └── chat.js                # 聊天状态
├── router/
│   └── index.js               # 路由配置
├── main.js                    # 应用入口
└── App.vue                    # 根组件
```

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

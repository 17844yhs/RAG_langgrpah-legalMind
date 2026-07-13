# 更新日志

本文件记录 LegalMind 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-07-10

### 新增

- ✨ **智能法律问答**：基于 LangGraph Agent 工作流的法律咨询对话，支持流式 SSE 输出
- 🔍 **案例检索**：通过 RAG（检索增强生成）技术检索相关法律案例，支持向量 + BM25 混合检索
- 📝 **法律文书生成**：支持生成民事起诉状、答辩状、律师函等法律文书
- 💬 **会话管理**：多轮对话历史持久化，基于 LangGraph Checkpointer（PostgreSQL）
- 🔐 **用户认证**：JWT 注册/登录认证系统
- 🎨 **前端界面**：基于 Vue 3 + Tailwind CSS 的现代化 Web 界面
- 🐳 **Docker 支持**：Docker Compose 一键启动 PostgreSQL + Redis 基础设施

# 贡献指南

感谢您对 LegalMind 项目的关注！我们欢迎任何形式的贡献。

## 开发流程

1. Fork 本仓库并创建您的特性分支：`git checkout -b feat/your-feature`
2. 提交您的变更：`git commit -m 'feat: add some feature'`
3. 推送到分支：`git push origin feat/your-feature`
4. 提交 Pull Request

## 提交规范

本项目采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 Bug |
| `docs` | 文档变更 |
| `refactor` | 重构（既不是新增功能也不是修复 Bug） |
| `test` | 添加或修改测试 |
| `chore` | 构建过程或辅助工具的变更 |
| `style` | 代码格式变更（不影响功能） |

示例：`feat: add BM25 hybrid retrieval`、`fix: correct JWT token expiration check`

## 代码规范

### Python

- 遵循 PEP 8 编码规范
- 使用类型注解（type hints）
- 注释使用中文，与现有代码风格一致
- 通过 `uv run pytest` 确保测试通过

### Vue / JavaScript

- 使用 Vue 3 `<script setup>` 组合式 API
- 组件文件名使用 PascalCase（如 `ChatMessage.vue`）
- 使用 Pinia 管理全局状态

## 环境设置

请参考 [README.md](README.md#快速开始) 中的快速开始指南配置开发环境。

## Pull Request 流程

1. 确保所有测试通过
2. 更新相关文档（如有 API 变更，更新 API 文档）
3. PR 标题使用 Conventional Commits 格式
4. PR 描述中清晰说明变更内容和动机
5. 关联相关的 Issue（如有）

## 报告 Issue

- 使用 Issue 模板创建
- 清晰描述问题或建议
- 附上错误日志、截图等辅助信息（如适用）

## 行为准则

请保持友好、尊重和包容的交流氛围。我们欢迎所有背景的贡献者。

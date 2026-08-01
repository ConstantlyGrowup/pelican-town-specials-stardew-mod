# Pelican Town Specials｜开发状态

> 本文件是开发状态唯一真源。设计内容回查正式技术设计，文档索引回查项目设计源索引；本文件只回答“当前哪个 Session、做到哪里、下一步是什么”。

## 当前状态

| 字段 | 值 |
|---|---|
| `overall_state` | `planned` |
| `project_phase` | `pre-development-bootstrap` |
| `product_implementation_started` | `false` |
| `active_session_id` | `2026-08-01-bootstrap-control-plane` |
| `active_session_state` | `committed` |
| `active_session_type` | `bootstrap-control-plane` |
| `current_task` | 无；MVP Task 1 尚未开始 |
| `blocker` | 无；产品开发仍等待用户另行授权 |
| `next_action` | 保持产品 Task 未启动；用户明确开始实施后，创建具体 Task Session 并按串行接力规则执行 |

## 当前 Git 状态事实

| 项目 | 当前值 |
|---|---|
| 仓库 | 已在当前目录初始化 |
| 初始分支 | `main` |
| `origin` | `https://github.com/ConstantlyGrowup/pelican-town-specials-stardew-mod.git` |
| 初始提交 | 本次 focused bootstrap commit |
| 远端操作 | 仅写入本地 remote 配置；尚未 fetch、pull 或 push |
| 用户已有代码修改 | 初始化前目录没有代码工程或 Git 历史可供保留 |

## 本次 Session 范围

- 创建项目级 Agent 入口、开发状态、约束摘要、开发阅读指南和初始 Session 记录。
- 创建最小 `.gitignore`，让控制面可提交，同时忽略用户指定的设计资料、开发计划、项目索引、密钥、工作区和构建物。
- 初始化本地 Git 并添加空远端 `origin`。
- 不创建业务代码、运行依赖、前端/后端骨架，不执行实施计划 Task 1，不派发 Subagent。

## 验收前检查

- [x] 控制面文件路径已建立。
- [x] 设计资料与本地规划路径已写入 `.gitignore`。
- [x] Git 仓库已初始化为 `main`。
- [x] `origin` 已添加，尚未进行任何远端读写。
- [x] `git status --short` 仅显示 `.gitignore`、`AGENTS.md` 和 `docs/` 未跟踪控制面。
- [x] `git check-ignore --quiet` 已确认 `design docs/`、`最初设计功能清点/`、`docs/architecture/`、`docs/plans/` 和项目索引均被忽略。
- [x] 控制面文件未被忽略，可作为 bootstrap focused commit 的候选范围。
- [x] 当前没有 `HEAD`，尚未创建初始提交。
- [x] 用户已确认文件范围、忽略边界和 Git 配置。
- [x] 已创建 focused bootstrap commit；提交后需要再次核验工作树干净。

## 状态规则

修改型 Session 只能按以下顺序推进：

```text
planned → active → verification → awaiting_user_acceptance → accepted → committed
```

任何状态冲突、脏工作树、重复活动 Session 或缺失下一步都必须停下并报告。Session 历史见 `docs/development/sessions/`，不能用历史记录覆盖本文件的当前结论。

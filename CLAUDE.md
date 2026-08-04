# Claude Code 项目入口

本文件是 Claude Code 从仓库根目录启动时的自动入口。项目通用边界和本项目专用执行协议分别位于以下文件：

@AGENTS.md
@claude-code/CLAUDE.md
@docs/development/REVIEW_PROTOCOL.md
@docs/development/CONTEXT_PACKET_SCHEMA.md

## 自治交接入口

Claude Code 必须把上述两个协议文件作为执行前置；如果它们与本文较早的静态 Task 清单冲突，以最新 Context Packet 和自治协议的动态依赖闭包为准。

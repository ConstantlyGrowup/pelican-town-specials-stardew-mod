# Session — Task 49 上游分析命名一致性与 0.85 阈值

| 字段 | 值 |
|---|---|
| session_id | 2026-09-03-task-49-analysis-consistency |
| status | committed |
| session_type | implementation |
| base_commit | 8ec667d |
| acceptance_contract_id | task49-analysis-consistency-20260903-v1 |
| user_authorization | 2026-09-03 用户要求优化上游 schema 内容一致性，特别是菜名，并将最终匹配阈值调到 0.85 |
| owner | Codex 主 Agent；新 luna_worker 实施；独立 detector 审阅 |
| revise_round | 0 |

## 范围与当前进度

- Packet：docs/plans/2026-09-03-task-49-analysis-consistency.md，READY_FOR_IMPLEMENTATION。
- 仅上游双语分析 prompt、Canonical 阈值与相关测试/文档；保留 schema、历史记忆、现有打分算法、temperature 省略及 Provider 调用次数。
- 本轮不进行付费 Provider 实测、push、tag 或 Release。
- git tracked diff 为空；未跟踪历史工作区/素材/发布说明维持原样，不纳入提交。部分既有临时目录访问权限警告不涉及本次明确文件。
- 已识别并报告文档旧状态：AGENTS/索引/P3 与 STATUS 发布事实不一致。用户本次阈值授权覆盖旧阈值，更新现行规范时保留历史 Session。
- 2026-09-03：冻结 A49-001–005 与 R49-01–05，进入实施。

## 验证过程

- 主 Agent 首次沙箱全量运行在 pytest tmpdir setup/cleanup 出现 WinError 5；独立 canonical registry 探针复现新建 basetemp 无法读取，非功能断言失败。已停止该次受限运行，改用获准的提升权限执行与全新隔离 output/task49/main-full-escalated；不修改测试绕过问题。
- 无文件 fixture 的领域测试先行 10 passed。Ruff 通过（扫描既有不可读历史临时目录时有警告），mypy 96 个源码文件无错误。
- 通过主 Agent 检查补充明确：归一化不能抹去主料/酱汁/风味/做法等菜品本体差异；中英文均覆盖 JSON Schema 与 JSON-only 请求。
- 主 Agent 提升权限完整后端回归：880 passed, 2 skipped, 2 warnings，107.86s。两个 skip 为环境相关，重复 ZIP 条目警告来自既有拒绝重复条目测试。独立审阅待完成。

## TASK_HANDOFF 摘要

- contract：task49-analysis-consistency-20260903-v1；A49-001–004 实施完成，A49-005 由主 Agent 同步；R49-01–05 均遵守，scope delta none。
- 实施文件：providers/prompts/analysis_v1.py、domain/canonical.py 与 provider/application/domain 三个测试文件；无需改 integration fixture。
- RED：在实现前，新增断言产生 6 个预期失败、68 passed（prompt 规则缺失和旧 0.80 常量/0.849、0.80 错误命中）。
- GREEN：最终 focused 76 passed（12.97s），provider 49 passed（9.76s）；Ruff PASS、mypy 96 源文件 PASS、diff-check PASS。测试在 process-local PTS_WORKSPACE_PATH 与独立 basetemp 下执行；未调用真实 Provider。
- 主 Agent：本会话 Codex；具体运行时模型/effort 未暴露，不推测。派发配置：自定义 luna_worker 角色（工具定义 gpt-5.6-luna / max）；worker 内部运行时未单独暴露模型标识/effort，因此不声称获得额外运行时自证。独立审阅使用 detector 角色（工具定义 gpt-5.6-sol / medium）。
- 真实输出稳定性、同菜多图 Hit@5 与命中准确率尚未实测。已有记忆的旧别名不自动迁移；正式 v1.5.4 安装包未改动。

## 独立审阅与收口

- detector：PASS，contract task49-analysis-consistency-20260903-v1，revise_round 0；A49-001–005 与 R49-01–05 全部核对，无 MUST_FIX/optional/new design/scope delta。
- detector 独立 focused：76 passed，13.82s；diff-check PASS。未调用真实 Provider，源码只读。
- 主 Agent 最终 focused 复验：76 passed，15.42s；与先前全量 880 passed/2 skipped 及 Ruff/mypy PASS 一起满足验收门。
- 状态：active → verification → detector PASS → auto_accepted → 本地 focused commit（本记录随同一提交收口，提交号见 Git 历史）。依据 AGENTS 普通 Task PASS 自动本地提交规则；不使用 detector 结论替代远端发布授权。
- focused commit 边界：仅 5 个后端源/测试文件、AGENTS/CONSTRAINTS/STATUS 与本 Session；设计、Packet 与索引按既有规则保持 ignored。不包含历史未跟踪素材、临时工作区或发布说明。
- 未 push、未提升版本、未创建 tag/Release，正式安装包仍 v1.5.4（旧 0.80 阈值）。后续真实同菜多图一致性/召回实验由用户另行安排；不能以本次自动测试声称真实效果已改善。

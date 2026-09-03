# Session — Milestone 12 量化评测规划

| 字段 | 值 |
|---|---|
| session_id | 2026-09-03-milestone-12-quant-evaluation-planning |
| status | committed |
| session_type | planning |
| base_commit | 54ffc68 |
| user_authorization | 根据 starvalley_quant_evaluation_plan_v2.pdf 构建下一里程碑并拆解 tasks；仅规划 |
| owner | Codex 主 Agent |
| implementation_started | false |
| plan | docs/plans/2026-09-03-milestone-12-quant-evaluation.md |

## 范围与来源

- PDF 三页已全文提取并渲染逐页核对；SHA256：73bf2d82c770785b8108ed6eb24b1b5c17be710dd8d19079af4535b0d9b8dbf6。
- 基线 Task 49 本地提交 54ffc68，阈值 0.85；正式 v1.5.4 仍 0.80。本轮未执行评测或付费调用。
- 规划 M12：Task 50 E2E → 51 数据构建 → 52 Current → 53 单 CPU Embedding → 54 汇总/人工清理。约 30 Canonical / 最低 60 Positive / 约 10 Negative；90 Positive 和大池规模为可选。
- 使用当前开发 workspace，简单脚本/表格/CSV，不创建评测平台、新服务、向量库或额外隔离环境。模型仅为评测期开发依赖。
- 开始前 tracked diff 为空；已有未跟踪素材/临时目录与此前一致，不纳入本次修改。
- 当前 M9 文档“不做命中率/Embedding”约束仍对产品实现有效；M12 计划单独提出开发期评测范围，并明确不扩张生产依赖。用户本轮规划要求并非真实运行/删除/发布授权。

## 待审阅内容

- 指标分母、错菜 HIT/模型故障的计数、标签不泄露、共用候选池、计时是否包含 query encoding。
- 模型选择依据为官方 model card；RAM/体积/速度没有填造数值。
- 提供图片、真实运行配置/额度、已有实验数据和最终人工判定/清理属于执行期外部输入，不阻止本次交付完整规划。

## 规划验证与交付

- 逐页核对 PDF 文本及三张渲染页，p1–p3 必需要求均映射到计划章节/Task；19 个 Acceptance ID 唯一，5 个 Task 顺序及依赖齐备。
- 代码可实施性核对：Registry.register 支持合法测试装载且校验图标 hash/16×16；RecallService 当前固定 retriever，计划只允许最小可选注入，复用真实判定；删除 Cookbook 不会删除 Canonical，清理说明已明确。
- 已同步 MVP 总计划、技术设计、第三期锚点、设计源索引和 AGENTS/CONSTRAINTS/STATUS；历史 M9/M10 范围与 0.80 发布事实保留。
- git diff --check 通过；正式计划/设计/索引仍按规则 ignored。没有 backend/frontend/依赖/业务数据变更，未运行产品测试（本轮仅文档规划），未启动 Task 50。
- 状态：active → verification（覆盖与闭包核对）→ awaiting_user_acceptance；尚未提交或推送。需要用户审阅规划后再进入实施/真实评测。

## 2026-09-03 规划 v1.1 调序（用户后续要求）

- 用户认可总体方向，要求可无人工前置推进的工作提前、人工介入后排。本轮只修改规划，未开始实施。
- 新增 Task 50 最小工具/模板/Current 与 Embedding 接线准备，使用 fake 数据/本地 CPU smoke 验收，不等待原图、人工标签或收费配置。
- Task 51/52/53 保留正式数据/Current 取数/Embedding 对照职责，工具部分移入 50；旧 50 E2E 改为 54，旧 54 汇总清理改为 55。默认 50→51→52→53→54→55，共 6 个任务。
- 标签核对必须先于正式计分；20 组原图不是 Task 50–53 前置。E2E 后移执行前按清单人工清除 synthetic Memory，避免影响当前 workspace 中正常用户链路；55 核验清理并处理剩余评测文件。
- 原有规模、指标、Top 5/0.85、轻量限制不变；不新增平台、服务或自动清理系统。
- 已同步详细计划 v1.1、MVP 总计划 v2.7/技术设计 v2.14、第三期锚点、索引 v3.12 与控制面；保持本 Session awaiting_user_acceptance，旧 v1.0 记录保留作历史。

- v1.1 文档复核完成：6 个 Task 顺序一致、24 个 Acceptance ID 无重复；原指标/规模保持，外部输入分阶段、标签先于计分与 E2E 前清理均已核对。git diff --check 通过；仅文档变更，未执行产品测试或实施。

## 2026-09-03 规划验收与执行授权

用户明确要求“开始实施，待到需要人工介入参与的时候停止”，据此接受 v1.1 调序并授权无人工前置的实施。规划 Session accepted → committed（本地文档 focused commit）；下一项 Task 50 单独建 Session。付费调用、人工标签和真实 E2E 仍按阶段停在实际外部输入处；不推送/发布或删除用户记忆。

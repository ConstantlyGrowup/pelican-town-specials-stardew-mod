# Session — Task 50 最小评测工具与对照接线

| 字段 | 值 |
|---|---|
| session_id | 2026-09-03-task-50-evaluation-tools |
| status | auto_accepted |
| task | M12 Task 50 |
| base_commit | 01d64e4 |
| acceptance_contract_id | m12-task50-evaluation-tools-20260903-v1 |
| revise_round | 1 |
| packet | docs/plans/2026-09-03-task-50-evaluation-tools-packet.md |
| user_authorization | 开始实施，待到需要人工介入参与的时候停止 |
| owner | Codex 主 Agent |

## 启动与冻结

2026-09-03 用户随后明确暂时搁置量化评测任务链，插入 Gus 故障续作 Task 56。Task 50 停在 verification、尚未独立验收/提交，已有修改与证据保留；未经再次授权不推进后续评测。

- 已读取入口、状态、规划 Session、约束、Review/Packet 协议、M12 v1.1 和相关设计/总计划/索引；已检查 tracked diff 与历史。规划已接受并在 01d64e4 独立提交；已知未跟踪素材和旧临时目录保留。
- 合同冻结 4 个既有验收项、7 个最小可实施性裁决。两个脚本、假数据测试、内部 retriever 注入及 evaluation 开发依赖组；不访问真实收费 Provider 或写入当前用户 Memory。
- 协作沿用每 Task 新 luna_worker 实施、detector 独立审阅、主 Agent 复验，PASS 自动本地提交，不 push/发布。
- 当前 Python 为 C:/Python313/python.exe；已装 torch 2.9.1、psutil 7.2.2。父 Agent 负责普通开发依赖及 CPU 模型准备，worker 负责冻结源码。真实本地 smoke 不作为正式性能/效果评测。
- 主 Agent 实际模型/effort 未由工具暴露，不推断；子代理按工具角色记录。

## 父 Agent 环境准备

- 官方 HF 模型元信息固定 revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`；文件位于 ignored `output/evaluation-m12/model/<revision>`，下载哈希清单 `output/task50/model-download.json`。普通 sandbox 网络连接被拒绝，按已授权模型准备范围 escalated 后成功。
- 现有 Python 用户环境新增 evaluation 依赖：sentence-transformers 6.0.1、transformers 5.16.1、huggingface-hub 1.29.0、numpy 2.5.2、scipy 1.18.1；torch 2.9.1+cpu 和 psutil 7.2.2 保留。pip report 在 output/task50/pip-install-report.json；未引入环境/包管理器/lockfile。
- 纯离线依赖 smoke PASS：4 CPU 线程，128 token 上限，3 条中文文本得到 3×384 有限向量。证据 output/task50/dependency-smoke.json；仅证明加载/编码可用，不作为正式性能或召回指标。实施 CLI 的完整 smoke 待代码交付后复验。

## 父 Agent 共享生产接线回归

- `python -m pytest backend/tests -q -p no:cacheprovider --basetemp=output/task50/parent-backend`：881 passed、2 skipped、2 个已有重复 ZIP 条目告警，126.55s。进程 PTS_WORKSPACE_PATH 指向 output/task50/parent-app；未接触真实用户 workspace。
- 实施期 CLI 初始 CPU smoke 成功；尚在补齐正式运行元信息/计量接线，结果不作最终验收。

## 父 Agent CLI 与真实检索器 smoke

- templates / dry-run / run --mode embedding（不带live）均成功，未加载模型/调用Provider/写Memory。假数据只在 output/task50/parent-cli-workspace 中装载。
- 对装载后的 JSONL/Registry reopen 复验发现日期/UUID/派生字段往返解析问题，已在实施期修复；validate 输出 valid=true、2 Canonical。
- output/task50/parent_retriever_smoke.py 调用真实 CPU Embedding + 真 Registry/RecallService + fake Matcher；Current/Embedding 均 MATCH_HIT、各2个纯检索计时样本、0付费调用。仅接线验证，不作为正式准确率。
- 使用真实 tokenizer 的752-token文本探针发现 BatchEncoding 不是dict导致截断漏记，实施期改用Mapping后复验 truncation=true。证据 output/task50/parent-retriever-smoke.json。

## 实施交接与父 Agent 验证

- luna_worker（角色配置 gpt-5.6-luna/max）交付六个冻结源码/测试/依赖文件，contract保持不变、rulings T50-R01–07、scope_delta none。红测试1 failed/16 passed；最终focused25 passed；未执行真实收费调用或用户Memory写入。
- 父 Agent focused独立复跑25 passed（3.33s）；Ruff PASS（四个既有历史目录访问告警）、mypy96 sources PASS、git diff --check PASS。生产diff仅内部Protocol/可选retriever注入。
- 进入verification，准备detector只读独立审阅；revise_round=0。

## 2026-09-04 恢复

用户明确授权继续 Task 50 及后续，直到实际需要人工参与时暂停。恢复既有合同，revise_round 仍为0；此前 detector 因额度限制未产生审阅结论，不算REVISE。当前基线 f5a99aa 已包含 Task 56，Task 50 未提交修改保留。asset_store.py 仅Git行尾状态差异，无内容diff，保持原样不纳入。补完独立审阅及当前基线回归后才验收，后续同菜标签需人工核对。

## 2026-09-04 首轮独立审阅 REVISE

- detector（gpt-5.6-sol/medium）按冻结合同复审：25专项PASS、Ruff/mypy97sources/diff-check PASS、离线CPU smoke PASS；提出四个既有合同问题，完整修复单 docs/plans/2026-09-04-task50-revise1.md。
- 必修：模板/重复seed保留既有数据清单；完整输入/源码/Matcher配置摘要；真实候选池与冻结输入一致且共用快照；真实缓存/预热RAM及截断统计。无新增设计/范围扩张。进入repair round1。
- 主 Agent 当前基线复验：25专项PASS；Task56 checkpoint/resume兼容4PASS。

## 2026-09-04 必需子代理额度阻塞与 E2E 素材更新

- 新 luna_worker repair1 启动后因使用额度耗尽退出，未产生修复代码；提示可用时间为 Sep7 12:24PM（工具原文，未核实其时区）。四项MUST_FIX仍待处理，revise_round1保持，不标为通过。按AGENTS指定模型不可用不得静默fallback；需用户授权主Agent直接修复/调整审阅流程，或指定模型额度恢复。
- 用户已提供20组真实照片：samples/20-E2E-pics/菜品图。只读核对1.png–20.png：20张PNG均可解析、SHA256均不重复；输入清单 output/evaluation-m12/e2e_inputs.json，20行空结果表 e2e_results.csv（completed/human_pass未填写）。这仅证明输入文件就绪，不代表完成真实E2E或人审。未调用Provider、未修改照片。

### 2026-09-04 用户授权修复执行例外
用户明确回复“允许，请继续”，授权主 Agent 直接完成四项 REVISE 修复，独立 detector 复审保留。更正上一条额度阻塞记录：重新检查发现 worker 已留下部分辅助函数与红测，并非完全未写入；保留并接续这些改动。合同及四项验收标准不变。

### 2026-09-04 repair round1 验证完成，待独立复审
主 Agent 按用户授权完成四项修复：既有模板保护和 seed 批次预检/ID复用；完整数据及相关源码摘要与有效 timeout/retry；调用前 manifest/冻结内容/资产校验和候选快照；保留真实 corpus vectors 后记录 cache/warm RSS 及 corpus/query 截断观察。生产召回策略不变。
最终专项：36 passed（24.97s，output/task50/parent-repair-final2）；Ruff PASS、mypy 97 files PASS、git diff --check PASS。修复中失败为图标 bytes JSON 序列化及不可变 DTO 测试夹具，均已修复并由最终专项覆盖。
离线 CPU 非正式 smoke：output/task50/repair-corpus-smoke.json，输入2条corpus/2条query；384维、max_seq128、4线程；common51.97/cache773.61/warm774.05MiB，warm增量722.08MiB；模型499557407bytes、加载14.31s；截断0且有实际token计数。此为工具测量链验证，不是Task53正式指标。
已交回 task50_review_resumed 做原四项封闭复审；尚未收到结论，不标记PASS或提交。

### 2026-09-04 独立复审 PASS / auto_accepted
原 detector task50_review_resumed（gpt-5.6-sol/medium）封闭 round1 独立复审 PASS；复跑36 passed/28.96s，Ruff/diffcheck PASS，四项原 MUST_FIX 均满足。主 Agent 复验36 passed、mypy97、实际离线CPU smoke均通过，按既有里程碑授权自动验收并创建本地 focused commit，不push。
非阻塞使用限制：空模板目录直接seed会安全拒绝；首次操作先seed再templates；已存在数据不覆盖。正式30/60/10数据、人审、收费调用与指标结果不在本Task完成范围。

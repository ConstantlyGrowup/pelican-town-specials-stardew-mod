# Session — Task 50 最小评测工具与对照接线

| 字段 | 值 |
|---|---|
| session_id | 2026-09-03-task-50-evaluation-tools |
| status | paused_by_user |
| task | M12 Task 50 |
| base_commit | 01d64e4 |
| acceptance_contract_id | m12-task50-evaluation-tools-20260903-v1 |
| revise_round | 0 |
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

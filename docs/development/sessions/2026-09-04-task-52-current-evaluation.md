# Session Task52 Current正式评测

session_id: 2026-09-04-task-52-current-evaluation
status: accepted
acceptance_contract_id: m12-task52-current-20260904-v1
revise_round: 0
base_commit: 4edaa64
packet: docs/plans/2026-09-04-task52-current-evaluation-packet.md

用户授权改用此前yibu端点Luna，额度用完停止并报告组别，够用则继续。按请求以现有额度为上限，不另要求金额；无自动充值。第1组Current70，第2组Embedding70；阶段验收串行。应用当前OpenAI/terra设置保留，评测内存配置使用yibu/luna。读取到进程和Windows用户PTS Key均存在但不同，历史yibu记录使用进程PTS环境；不打印key、不自动换用其他key。先完成最小批次停止/逐条保存包装，调用前冻结合同，真实评分与原生产决策一致。当前既有工作树只有asset_store无内容diff的stat变动，保持不动。

## 凭据预检更新（尚无live调用）
进一步仅检查格式，进程及Windows用户PTS_OPENAI_API_KEY均为sk-proj格式且不同；应用当前OpenAI端点，无法确认Yibu凭据归属。不能把可能属于其他服务的Key发往yibu。R01改为明确Yibu专用PTS_YIBU_API_KEY（进程或Windows用户），不回退现有PTS_OPENAI_API_KEY。worker继续离线runner/fake验证，暂不执行live。第1组Current0/70，第2组Embedding0/70；这是缺少可确认的凭据，不是额度耗尽。

## 暂停点与真实完成范围
凭据专用PTS_YIBU_API_KEY进程/Windows用户均未配置。父Agent已请求用户配置此项，不再重复模型/预算授权。新worker task52_runner（派发配置luna_worker/gpt-5.6-luna/max；不采用其无法核实的自报模型名称）长时间未产出文件，父Agent中断并索取handoff：仅完成只读检查，run_evaluation.py与test_run_evaluation.py均未创建，无pytest/Ruff/真实Provider请求。不可声称离线runner实现完成。
已完成：本轮模型/剩余额度授权记录、Task52冻结Packet、frozen-v1的30/60/10及资产/57行Registry只读预检PASS，next_run_plan更新。未完成：逐条保存/额度停止runner及fake验证、真实Current取数、Task52独立最终验收。准确进度第1组Current0/70、第2组Embedding0/70，费用请求0；原因是未确认Yibu凭据，非额度耗尽。用户配置后先完成runner验证再从Q001开始，禁止将现存其他providerKey送往Yibu、禁止自动改用别的Key。未提交或推送Task52。

## 凭据恢复与实施分工
用户确认已配置；专用PTS_YIBU_API_KEY在Windows当前用户级存在，进程级不存在。仅记录存在性，不导出凭据。恢复active，尚无live请求。最小机械集成裁决：新luna_worker quota_guard负责output/task52/quota_guard.py及test_quota_guard.py；父Agent负责run_evaluation.py逐条调用/落盘编排。范围仍为一次性批次wrapper，生产代码与合同不变。

实施证据：quota_guard新luna_worker完成两文件，6项fake测试及Ruff PASS；父Agent整合逐条runner和停止/保存/拒绝重放测试，共7 passed，Ruff PASS。首次pytest因模块路径缺失collection失败，显式PYTHONPATH后通过。真实工作区离线预检PASS：30/70/60/10，数据hash与Task51一致，候选snapshot一致，无Provider请求。请求事件单独计数以包含运输失败，响应次数另记。独立readiness detector进行中。

独立detector task52_readiness返回readiness PASS（不等于Task52最终验收）；其MockTransport使用真实gateway retries=2验证quota仅1次HTTP。父Agent已启动Current live批次，输出output/evaluation-m12/current-run，尚待进度。

## Current完整批次结果
已真实执行70/70，63次HTTP请求、62次响应（1次运输失败后按原策略重试）；8条无候选查询不调用Matcher。额度未耗尽，0最终Provider错误。正例Top5包含60/60、最终正确命中59/60；负例误命中0/10。唯一正例未命中Q036，原标签与全部输入不改。输出output/evaluation-m12/current-run/results.jsonl、results.csv、metrics.json、run.json、retrieval.json、progress.json。父Agent只读核验70唯一结果及27原有Registry行逐列未变、总行57。进入独立最终核验，不能将readinessPASS混作最终PASS。

最终detector PASS：独立核验70唯一且有序结果、CSV/JSONL一致、59/60正确命中、60/60包含、0/10负例误命中、0错误、全部data/config/source/prompt/wrapperhash及70x10timings。Q036置信度0.84，低于固定0.85，保留真实miss。父Agent复核通过，Task52 auto_accepted关闭；纯执行Task按M12计划不强制代码提交，控制面待里程碑汇总，不push。用户再次要求继续，按既有授权进入Task53。


## 2026-09-04 Milestone 12 整体验收

用户明确确认Task50–55及追加指标整理/CPU模型清理完成，并授权提交推送MVP及更新过时文档。本Session已关闭；历史中待人审/暂停/未授权文字仅记录当时事实，不再是当前下一步。当前结论见 docs/development/M12_QUANTITATIVE_RESULTS.md。本次无产品改动，不触发Release；本Session记录纳入M12文档收口提交。

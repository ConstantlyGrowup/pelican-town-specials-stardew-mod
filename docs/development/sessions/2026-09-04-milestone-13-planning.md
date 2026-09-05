# Session：M13 草稿管理与视觉复用规划

session_id: 2026-09-04-milestone-13-planning
status: accepted
session_type: planning
base_commit: 7768172

用户要求设计三项新需求：主页默认10条分页、创建/更新时间排序；语义记忆命中后原图与Canonical图标源图视觉相似度>=75%才复用图标，低分重画保留文字；所有Gus生成结果在重新生成旁提供游戏风格说明输入。

本轮仅规划，未获得实施/付费调用/新提交推送授权。Task57–59设计位于docs/plans/2026-09-04-milestone-13-draft-visual-regeneration.md。Task57合并主页分页与排序；Task58为双图视觉节点、部分文字复用与Task56检查点兼容；Task59为可选说明的完整重生成。

主Agent核对当前orchestrator、Provider协议、checkpoint、Canonical归档；只读explorer核查UI/API：当前列表全量UUID顺序、Summary缺createdAt；Gus PATCH无source修改入口，generate无body；default续作与restart完整重生成分离。设计新增排序分页参数/元信息、视觉判定独立状态和可选重新生成说明，保留旧结果失败回滚。仅规划内部API接点，不修改现有产品机制或生产文档合同。

默认设计（待审阅）：更新时间倒序、创建/更新时间各双向；低视觉分只重画图标；视觉Provider错误保存进度并手动继续；用户输入说明点击既有完整重新生成，绕过记忆，最多500字符、与原context分开。原图+最终图标仍生成新preview，不缓存整张preview。原始已命中文字及共享Canonical资产不被低分重画覆盖。

验收准备覆盖分页边界/全局排序、0.75及0.749、命中/未命中、双图角色、个人/试用gateway、失败续作不重复Matcher/视觉节点、反馈进入真实prompt与旧成功稿保护。完整代码Packet在设计认可后逐Task冻结；不声称已READY_FOR_IMPLEMENTATION。

当前下一步：用户审阅设计。M12保持已关闭；现有asset_store.py无内容diff状态保留。本轮无产品改动、无模型调用、无提交推送或发布。

只读设计复核：explorer确认Task59接口/续作/原子保护一致；提出Task57需保留既有nextCursor:null及total，主Agent已明确写入设计，无其他关键矛盾。文档diff-check通过；复核仅为规划可行性，不是实现或产品验收PASS。

## 2026-09-05 实现候选接管审计

用户要求先检查代码、更新状态、再补完。工作树实际已有Task57–59候选实现，但控制面未记录实施来源或验证，因此此前“仅规划”状态已纠正，不能据代码量判定完成。

- Task57审计REVISE：时间降序错误地反转同时间draftId次序；缺10/21与过滤后边界；无效/越界URL及删除末页没有回写有效页。Task57已建立独立恢复Session并先行修复。
- Task58审计REVISE：低分视觉判定后图标生成失败会丢判定并重复收费；SOURCE完好但16图损坏未降级；低分新图标authority仍误记CACHE_REUSED；需补双图角色/试用链路测试。
- Task59审计REVISE：原始contextText未真正拼入Provider prompt；UI恢复同轮错误调用restart=true；网络失败/取消清空说明。必须在各自后续Session修复。

三个Task保持串行；Task58/59候选修改受保护，不在Task57中顺手变更或验收。

## 规划执行结果

用户随后明确要求检查代码、更新状态并继续完成。Task57–59均按独立Session与冻结合同实施、审阅并PASS；集成期390px布局缺口也已修复并独立PASS。规划Session关闭，当前人工门与完整证据见`2026-09-05-milestone-13-integration-verification.md`。

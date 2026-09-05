# Session：Task 60 收集品分页

session_id: 2026-09-05-task-60-cookbook-pagination
status: auto_accepted
session_type: implementation
base_commit: 27cdc51

## Context Packet

- objective: 收集品页面默认每页展示10条，保留现有归档顺序、预览、选择、批量删除与打包行为。
- acceptance_contract_id: `m13-t60-cookbook-pagination-20260905-v1`
- allowed_files: `frontend/src/features/cookbook/CookbookPage.tsx`、对应测试、双语copy、局部CSS、M13计划与开发控制面。
- behavior: 页码使用`page` URL query；无效页归一为1，数据变化或删除末页最后条目后回退到有效末页；总收集数显示全量，当前页最多10条；仅加载当前页详情；跨页选择保持。
- exclusions: 不改变Cookbook API/schema、归档排序、删除级联、打包选择协议、Provider与Release版本。
- verification: CookbookPage专项测试、frontend全量、ESLint、TypeScript/Vite build、桌面与390px页面检查、独立detector。

## Planning ruling

现有`GET /api/v1/cookbook`已返回完整稳定列表且仅CookbookPage直接消费；本Task使用前端分页，避免改变既有Page泛型和潜在旧客户端行为。详情查询切片到当前页，获得实际请求量下降。后端大集合传输优化可在有明确规模指标后单独设计。

## Implementation and verification

- CookbookPage按现有归档顺序切分，每页最多10条；`page`写入URL，第一页省略参数，列表加载后再归一非法/越界页，避免直达第二页被首帧空数据重置。
- 详情查询仅覆盖当前页；全量收集数、跨页selection store、批量删除和打包入口保持。删除稀疏末页后自动回到有效页。
- 空槽保持Task60前的最少8格视觉规则；390px以下收集品网格专属两列，不修改主页共享分页样式。
- 首轮专项发现URL首帧归一问题并修复。最终CookbookPage 11/11、frontend全量231/231、ESLint、TypeScript/Vite build PASS；仅既有大chunk warning。
- Playwright隔离验收：1440px与390px均为第一页10条/第二页1条，第二页URL为`?page=2`；390px `scrollWidth=clientWidth=390`、overflowing为空。测试服务器三条401来自未拦截装饰资源，不涉及Cookbook API或分页行为。
- detector round0因共享`.draft-pagination`候选样式超范围判REVISE；该并发候选已完整收回。round1确认共享规则与HEAD一致、当前CSS仅收集品移动端规则，裁决PASS；scope delta none。
- 未改后端、OpenAPI/schema、归档顺序、Provider或版本链；未push、未发布。

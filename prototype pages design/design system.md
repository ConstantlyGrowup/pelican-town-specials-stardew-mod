# Pelican Town Specials Design System

版本：v1.0
日期：2026-08-09
状态：Task 21 视觉推导基线，可用于开发规划，不改变业务契约

## 1. 文档角色

本文件把 Design Brief、页面清单、Stitch P0 原型与当前 React 页面收敛为一套可实施的前端设计系统。
它定义视觉结构、组件边界、页面密度、交互状态和无障碍底线。
它不新增路由、字段、API、状态机、业务操作或移动端需求。
Stitch HTML 是视觉参考，不是可直接复制的生产实现。
当前 React 行为和服务端状态真值必须保留，视觉层只负责清晰表达。

## 2. 产品体验模型

产品主线是：现实菜品 → 获得鹈鹕镇身份 → 成为收集品 → 打包 → 带进游戏。
产品母气质是温暖、日常、手工、小镇生活与轻微幽默。
产品不是 AI 控制台、开发者后台、酒馆官网或可操控角色的网页游戏。
游戏感负责“属于 Pelican Town”，信息架构负责“完成真实任务”。

## 3. 视觉架构

全站共享一个 App Shell、像素构造方法、排版节奏、状态语言和交互反馈。
Warm Pelican 是母主题，用于首页、Create、Ask Gus、Cookbook、导出与设置。
Joja Blueprint 是受控子主题，只用于 Blueprint 的工作台和相关 Picker。
Cookbook 是原作浓度最高的收藏界面，但仍使用同一 Shell 与状态组件。
Pack、Bring In-Game、Settings 是派生页，不建立第三套视觉语言。

## 4. 页面原作浓度

| 表面 | 浓度 | 设计重点 |
|---|---:|---|
| Home Hero | 很高 | 世界观、双入口、第一记忆点 |
| Ask Gus | 很高 | 鉴定、真实阶段、结果揭晓 |
| Cookbook | 最高 | 收藏格位、选择、详情面板 |
| Create | 高 | 模式仪式感与上传槽位 |
| Cookbook Detail | 高 | 已冻结游戏物品信息 |
| Blueprint | 中高 | Joja 蓝图与高效编辑并存 |
| Pack Menu | 中高 | 收集品派生的整理台 |
| Bring In-Game | 中 | 安装步骤可读性优先 |
| Settings | 中低 | 克制、明确、技术信息优先 |

## 5. 像素构造原则

材质通过多层结构建立，不通过单一橙色背景建立。
标准 raised surface 顺序为：深色外轮廓 → 主框 → 内缘 → 内容面 → 顶左高光。
标准 recessed surface 顺序为：深色外轮廓 → 内侧暗边 → 内容面。
结构边缘以 2px、4px、8px 阶梯为主，所有关键尺寸落在 4px 网格上。
深度使用硬阴影和 inset 高光；不使用模糊阴影、玻璃、霓虹或柔光。
核心容器使用 0–4px 圆角；像素切角优先于 CSS 大圆角。

## 6. Warm 语义色

| Token 角色 | 基准值 | 用途 |
|---|---|---|
| `ink-strong` | `#3B160D` | 外轮廓、正文深色、硬阴影 |
| `wood-deep` | `#6B2D18` | 主木框、危险动作外层 |
| `wood-main` | `#934821` | 导航、木质主体、次级按钮 |
| `wood-mid` | `#C56A2D` | 边框过渡、按压面 |
| `gold` | `#E89A3A` | active、hover、强调 |
| `cream` | `#F6C76A` | Tooltip、主要暖色内容面 |
| `highlight` | `#FAD98B` | 顶左高光、选中内缘 |
| `paper` | `#FFF8F6` | 长正文、表单、安装说明 |
| `page-warm` | `#6F2C18` 附近 | 场景外背景，需实测对比度 |

颜色值进入生产代码前必须转为语义 token；组件不得散落品牌 HEX。
成功、警告、错误必须另有 icon、边框和文字标签，不能只靠绿色、黄色、红色。

## 7. Blueprint 语义色

| Token 角色 | 基准值 | 用途 |
|---|---|---|
| `blueprint-ink` | `#0A1428` | 蓝图外轮廓、正文深色 |
| `joja-blue` | `#2152A3` | 主框、focus、主动作 |
| `blueprint-cyan` | `#A4D3EE` | 分组标题、次级面 |
| `blueprint-paper` | `#E1EBF4` | 编辑纸面 |
| `blueprint-white` | `#FFFFFF` | 输入与高对比内容区 |

Blueprint 允许 8px 点阵、模块编号、测量线和工具图标。
Blueprint 不使用 Warm 色简单换 hue，也不做 CAD、IDE、HUD 或企业蓝后台。
危险动作仍使用全站统一 danger 语义，不创造“蓝色危险态”。

## 8. 排版

标题、导航、按钮、Tab、Badge 和短标签使用有角色感的 display 字体。
中文正文、说明、错误、设置和安装步骤使用高可读 sans-serif。
内部名、版本、阶段编号和技术元数据可使用 monospace。
正文默认 15–16px、行高 1.6–1.8；不可用 12px 像素字体承载长中文。
页面只允许一个可见 `h1`；分组按 `h2`、`h3` 顺序组织。
字体文件必须可发布，并在第三方声明中登记；未确认前使用系统中文回退栈。

## 9. 间距与桌面布局

基础单位为 4px；常用间距为 8、12、16、24、32、48px。
桌面目标视口为 1440×900，最小可操作宽度为 1024px。
全站内容最大宽度建议 1200–1280px，并保留 24–32px 安全边距。
低于最小宽度可压缩装饰、堆叠次要栏或提示扩大窗口，但不能破坏任务。
1440×900 与 1024px 支持宽度均不得出现页面级横向滚动。
Cookbook 保持固定 slot 节奏；Blueprint 在桌面保持预览 / 编辑双栏。

## 10. App Shell

顶部导航是固定产品锚点，一级入口严格为：首页、开始创作、收集品、设置。
导航使用木质 sign / menu bar；active 项以金色多层框表达，而不是下划线或 pill。
产品名保持可见，但不伪造 Stardew Valley 官方 Logo。
通知、账户等当前产品不存在的入口不得从 Stitch 原型移植。
主内容区提供跳过导航入口和稳定的 focus 起点。
页面主题通过 `data-theme="warm|blueprint|cookbook|utility"` 或等价语义切换。

## 11. 基础 Surface

`PageFrame`：约束最大宽度、背景、页标题与主内容起点。
`WarmPanel`：暖木多层框，承载模式、收集品和故事性内容。
`PaperPanel`：Warm 框内的高可读纸面，承载长正文和表单。
`BlueprintPanel`：深蓝轮廓、蓝图纸面、可选点阵纹理。
`SectionFrame`：较轻的分组边界，不重复完整七层木框。
`Modal`：遮罩 + 多层实体框；必须有标题、关闭动作、焦点陷阱和返回焦点。
`Tooltip`：暖色游戏物品语法；仅补充信息，不承载必须点击的关键操作。

## 12. 输入组件

Input、Textarea、Select、NumberInput 使用硬边、多层 focus 与足够点击高度。
标签必须与控件程序化关联，必填、说明和错误分别占稳定位置。
错误态包含错误 icon、边框变化、文本和 summary 链接，不能只改颜色。
禁用态保留可读文本，不通过过低 opacity 使内容消失。
Checkbox / Radio 的 checked 状态需要形状或符号；键盘 focus 必须独立可见。
Image Upload 是 inventory slot / photo frame，不使用通用虚线 SaaS dropzone。
Picker 是可搜索的主题 Modal；搜索、分页和关闭均可通过键盘完成。

## 13. 动作组件

Primary：页面唯一主推进动作，具有 raised frame 和明确 pressed 位移。
Secondary：保留结构但降低填充对比度，用于返回、刷新、验证或次级选择。
Danger：深木 / 红棕语义 + danger icon + 明确文案；必须经过确认面。
Icon Button：必须有可访问名称和可见 Tooltip，点击区域至少 36×36px。
Disabled：不得响应 hover / press，且说明不能执行的原因或由上下文明确表达。
Loading Button：保留原文义与宽度，加入状态文本，不伪造百分比。

## 14. 游戏专属组件

`DishSlot` 标准为方形、硬边、recessed；图标使用 `image-rendering: pixelated`。
`EmptySlot` 保留轮廓和低对比占位符，不表现为错误或可用菜品。
`SelectedSlot` 使用 corner marker、内缘和文字计数，不能只改背景色。
`ItemTooltip` 展示菜名、描述、原料、恢复、Buff 与售价。
`StatRow` 统一 icon、标签、数值对齐；Energy / Health 为派生展示值。
`IngredientChip` 可显示 icon、名称、数量和删除动作；Blueprint 允许编辑数量。
`PreviewFrame` 同时容纳真实预览、16×16 图标、下载动作和 stale corner tag。
下载按钮使用产品像素 glyph，不继续使用圆形浮层式现代图标。

## 15. 状态语言

| 状态 | 结构表达 | 行为边界 |
|---|---|---|
| loading | skeleton / 小型 sprite + 文本 | 不阻塞取消或返回 |
| empty | 空 slot / 空面板 + 下一步 | 不伪造示例业务数据 |
| uploading | 上传槽 active + 文件状态 | 反映真实上传请求 |
| generating | 当前阶段高亮 + 已完成计数 | 不显示虚构百分比 |
| regenerating | 旧结果保留 + 新 attempt 覆层 | 成功后才整体替换 |
| reviewable | 结果面板 + 合法动作组 | Ask Gus 严格三操作 |
| stale preview | preview corner tag + 主更新动作 | 非错误，不覆盖旧预览 |
| warning | amber frame + icon + 文案 | 可继续时说明后果 |
| error | error frame + summary + 恢复动作 | 使用脱敏真实错误 |
| archived | 稳定 badge / 收藏 slot | 不可编辑、不可重生成 |
| selected | marker + frame + 计数 | 不只依赖颜色 |
| disabled | 结构保留、对比度降低 | 不隐藏不可用原因 |
| success | 完成框 + 下一步 | 不用长动画阻塞流程 |

## 16. Generation Progress

生成进度只消费服务端 attempt、current stage、succeeded stages 与 total stages。
当前阶段可使用呼吸、像素高亮或 Gus 小 sprite；完成阶段使用稳定 check。
阶段变化通过 `aria-live="polite"` 宣告，取消动作始终可键盘访问。
断开、刷新或切页后必须 hydrate 同一服务端任务，不显示“从头开始”的假象。
Reduced Motion 下取消呼吸和位移动画，保留静态 frame 与文本变化。

## 17. 页面应用规则

Home：紧凑 Hero + 两个并列模式入口 + 三步故事 + 草稿 Dashboard；首屏暗示下方工作区。
Create：Ask Gus 与 Blueprint 是主题明确、同等重要的模式卡；上传完成后显示真实缩略图。
Ask Gus：低信息密度；原图 / Gus / 阶段 / 揭晓为主；结果只显示接受、完整重新生成、拒绝。
Blueprint：左侧预览、图标与状态；右侧基本信息、原料、属性、校验与动作。
Cookbook：slot grid 为主、详情 / Tooltip 为辅；不得显示或暗示来源模式。
Cookbook Detail：表现“已正式收藏”的稳定对象；只读，可下载和删除，不可编辑。
Pack Menu：复用 selected slots、Warm Panel、包名表单和 validation，不建立新主题。
Bring In-Game：使用 numbered steps 和高可读纸面，路径、依赖、错误优先于装饰。
Settings：继承 Shell、PaperPanel、Input 与 Button；Gus 和蓝图场景元素不得介入技术设置。

## 18. Motion

Utility motion 为 100–180ms，用于 hover、focus、tab 和状态切换。
Game feedback 为 180–350ms，用于按压、slot 选择、Tooltip 和阶段变化。
Moment motion 为 350–700ms，只用于结果揭晓、归档、打包成功和首次 Hero。
动效不延迟 API、不阻止跳过、不改变真实状态时序，也不强闪烁。
统一提供 `prefers-reduced-motion` 降级：duration 近零、取消位移、保留状态终点。

## 19. 无障碍底线

正文与背景、控件与背景必须达到 WCAG AA 对比度目标。
所有交互可用键盘完成，并有不被 hard shadow 淹没的 `:focus-visible`。
每页唯一 h1；表单 label、描述、错误使用 `aria-describedby` 或等价关联。
Dialog 打开后聚焦标题或首个控件，Tab 不逃逸，Escape 关闭并把焦点还给触发器。
状态、selected、error、success 由 icon + frame + label + copy 联合表达。
图像 alt 描述业务对象；纯装饰像素纹理和边框从辅助技术隐藏。
Toast 或临时反馈不得成为唯一证据；关键错误保留在页面中。

## 20. 资产与图标边界

官方、用户生成、产品自绘和通用功能资产必须区分来源。
每个可发布字体、图标、官方素材和 Hero 资产需要 provenance / third-party 记录。
Stitch 原型中的 Material Symbols、通知与账户图标不能直接进入产品。
产品功能图标应统一为小型像素 glyph，不混用现代 outline icon。
用户菜品照片保持原貌，不做强制像素化；仅游戏 icon 使用 nearest-neighbor 展示。

## 21. 从原型到生产的迁移规则

保留：页面构图、Warm/Blueprint 对比、像素边框、slot 节奏、信息层级与关键场景资产。
重做：Tailwind 原子类、Material Symbols、散落 HEX、假数据、无语义 div 与仅鼠标 hover 行为。
不复制：通知 / 账户入口、不存在的字段、伪造进度、来源模式、Ask Gus → Blueprint 路径。
现有 React Query、React Hook Form、路由、API 类型和生成状态管理保持不变。
视觉组件应渐进提取，避免一次性重写页面业务逻辑。

## 22. Task 21 实施边界

允许：新增展示组件、样式 token、主题类、可访问语义、视觉回归与无障碍测试。
允许：为了现有状态完整表达而补充 loading、empty、error、disabled、focus、stale 和 confirm UI。
禁止：修改后端、OpenAPI、Draft 状态机、生成时序、Archive 不变量或 Export 协议。
禁止：新增路由、登录、云同步、移动端流程、聊天、社区或市场。
禁止：恢复 Ask Gus → Blueprint，或给 Ask Gus 增加字段级编辑 / 局部重试。
禁止：Cookbook 暴露来源模式，或让 Archived Dish 可编辑 / 重生成。

## 23. 规划切片建议

切片 A：冻结 tokens、字体回退、背景、App Shell、基础 Surface、Button、Input、Status。
切片 B：Home、Create 与共享上传 / 草稿卡，建立 Warm 核心体验。
切片 C：Ask Gus 全状态与 Generation Progress，覆盖初次生成、重生成、失败和取消。
切片 D：Blueprint 双栏、Picker、STALE_PREVIEW 与表单错误，建立受控 Joja 子主题。
切片 E：Cookbook grid、slot、Tooltip、详情与删除确认，完成最高原作浓度页面。
切片 F：Pack、Bring In-Game、Settings 派生，并统一 utility 密度。
切片 G：视觉基线、键盘流程、focus trap、对比度、Reduced Motion 与最终验收脚本。

## 24. 设计完成定义

5–10 秒内能理解这是把现实菜品带进 Stardew Valley 的本地工具。
Home 同时具有品牌入口与 Dashboard，不被 Hero 吞没。
Ask Gus、Blueprint、Cookbook 视觉各有主题，但明显属于同一产品。
核心 Panel 有真实多层像素构造，不再是白卡 + 1px 灰边 + 10px 圆角。
Blueprint 可快速扫描，Cookbook 是 slot grid，Settings 与安装步骤仍清晰易读。
所有真实业务状态均有一致表达，不伪造进度或隐藏失败。
1440×900 视觉基线稳定，1024px 宽度可完成完整流程。
键盘、焦点、Dialog、aria-live、错误 summary、颜色对比和 Reduced Motion 通过验收。
现有产品测试、OpenAPI、构建、Windows bundle smoke 与 Mod ZIP 验证无回归。

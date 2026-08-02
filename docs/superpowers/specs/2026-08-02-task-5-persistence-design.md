# Task 5 持久化设计：工作区、原子 JSON Repository 与 Asset Store

> 状态：基于已批准的 MVP 技术设计与实施计划；Task5 已获用户授权启动，具体实现与验证结果记录在对应 Session。

## 1. 目标与边界

Task5 为 Task4 的领域记录提供可靠的本地文件持久化。它负责工作区初始化、JSON 记录的安全写入与恢复、Draft/Archive Repository、图片和导出资产登记，以及短期可恢复删除。

本 Task 不包含 API 路由、Secret Store、模型调用、前端页面、Launcher、数据库、Mod 编译或真实素材处理。资产存储只负责字节、元数据、哈希和安全相对路径；图像理解、缩放和合成属于后续 Asset Pipeline。

## 2. 总体方案

工作区采用 JSON 实体记录加独立资产文件的结构。实体记录和资产内容是真实来源，index.json 只用于加速列表查询并可以从实体记录重建。Repository 对外只返回领域对象和不透明资产引用，业务层不需要知道实际磁盘路径。

所有 JSON 更新都在目标文件同目录创建唯一临时文件，使用 UTF-8、LF、两空格缩进和稳定键顺序序列化，写入后 flush 并 fsync；替换前保留一份 .bak，最后使用 os.replace 完成提升。主文件损坏时，只有通过领域 Schema 校验的 .bak 才能恢复。

## 3. 组件职责

### 3.1 WorkspacePaths 与工作区记录

WorkspacePaths.create(root) 创建技术设计 §8 规定的目录：app-state、drafts、cookbook、assets、exports、staging 和 trash，并保证初始化可重复。工作区记录首次创建时生成 D<YYYYMMDD> 的 authorName 并持久化；后续启动必须读取原值。bootstrap.json 只记录 schemaVersion 与当前 workspacePath。

迁移采用“复制到目标 staging → 校验文件数量与 SHA-256 → 原子切换 bootstrap”的顺序，旧工作区保留，不在本 Task 自动删除。

### 3.2 DraftRepository

草稿实体位于 drafts/<draftId>/record.json，列表索引位于 drafts/index.json。save(record, expected_revision) 只接受当前 revision 与 expected revision 一致的写入，并在成功时递增 revision；冲突必须抛出可识别错误，不覆盖新数据。读取时先校验主记录；主记录损坏时只使用通过验证的 .bak。索引损坏或缺失时从实体记录重建。

### 3.3 ArchiveRepository 与 tombstone

归档实体位于 cookbook/<dishId>/record.json。add_immutable(record, idempotency_key) 对相同幂等键重复调用返回同一快照，不修改已有 ArchivedDish；不同内容不能静默覆盖相同 ID。删除时把整个记录目录移动到 trash/cookbook/<dishId>，从活动索引移除，并写入 CookbookTombstone，新导出不可再次选择已删除收集品。

### 3.4 FileAssetStore

put(data, metadata) 先校验允许的媒体类型、大小、扩展名和图像尺寸，再计算小写 SHA-256，使用 UUID 文件名和前两位分片目录写入文件，最后登记 AssetRef。资产记录只能保存 POSIX 风格相对路径；绝对路径、路径穿越和不存在的文件都必须被拒绝。重复内容可以复用同一哈希资产，但不得泄漏实际绝对路径。

## 4. 数据流与错误处理

~~~text
领域记录 / 资产字节
        │
        ▼
规范化序列化与校验
        │
        ├─ JSON：同目录 tmp → flush/fsync → .bak → os.replace
        └─ 资产：临时字节文件 → SHA-256 / MIME / 尺寸校验 → 登记 AssetRef
        │
        ▼
实体记录与内容成为事实源，索引按需重建
~~~

持久化失败不得留下被当作成功结果的半写文件；临时文件可在下一次初始化时清理。revision 冲突、记录不存在、幂等键冲突、资产校验失败和路径越界必须有稳定、可测试的异常边界。错误信息不得包含 API Key 或完整图片内容。

## 5. 验收重点

- 原子替换失败时旧文件保持不变；
- .bak 仅在通过 Schema 校验时恢复；
- Draft revision 冲突不会覆盖已有记录；
- Draft/Archive 索引可以从实体重建；
- Archive 重复幂等，删除生成 tombstone 且移动到 trash；
- AssetRef 的哈希、大小、媒体类型、尺寸和相对路径正确；
- 工作区首次创建生成并持久化日期 AuthorName，再次创建保持原值；
- 持久化测试和 Task4 领域回归测试全部通过。

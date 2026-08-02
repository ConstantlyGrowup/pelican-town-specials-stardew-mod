# Task 5 持久化实现计划

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: 为 Task4 领域记录建立可恢复的本地工作区、原子 JSON Repository、资产存储和短期回收站。

Architecture: 以 JSON 实体记录和独立资产文件作为事实源，索引仅作为可重建加速层。所有记录更新通过同目录临时文件、flush/fsync、.bak 和 os.replace 完成；Repository 负责 revision、恢复、索引和 tombstone，Asset Store 负责字节校验、哈希和安全相对路径。

Tech Stack: Python 3.13、Pydantic 2、pytest、标准库 json/hashlib/os/shutil/pathlib/uuid，现有 Task4 领域模型。

## Global Constraints

- MVP 使用 Windows 本地 Web、FastAPI + Pydantic、JSON 工作区；本 Task 不引入数据库。
- 默认工作区为 %LOCALAPPDATA%\\PelicanTownSpecials\\workspace；浏览器不直接访问任意本地文件路径。
- JSON 使用 UTF-8、LF、两空格缩进、稳定键顺序，时间统一为 UTC ISO 8601 并以 Z 结尾。
- 所有写入先在同目录创建 .<name>.<uuid>.tmp，刷新并 fsync 后保留单份 .bak，再使用 os.replace 提升。
- 索引是加速层，可以从实体记录重建；实体记录与资产内容才是事实源。
- AssetRef 只允许 POSIX 风格安全相对路径；API DTO 不暴露绝对路径。
- API Key 不属于工作区；本 Task 不实现 Secret Store，也不写入任何 secret。
- 新功能遵循 TDD：先写失败测试并观察预期失败，再写最小实现并复跑测试。
- uv 不是产品运行或 Task5 前置工具；不提交 Python lockfile 或虚拟环境。

---

### Task 5: 工作区、原子 JSON Repository 与 Asset Store

Files:
- Create: backend/src/pelican_town_specials/persistence/__init__.py
- Create: backend/src/pelican_town_specials/persistence/atomic.py
- Create: backend/src/pelican_town_specials/persistence/workspace.py
- Create: backend/src/pelican_town_specials/persistence/repositories.py
- Create: backend/src/pelican_town_specials/persistence/asset_store.py
- Create: backend/src/pelican_town_specials/persistence/trash.py
- Test: backend/tests/persistence/__init__.py
- Test: backend/tests/persistence/test_atomic.py
- Test: backend/tests/persistence/test_repositories.py
- Test: backend/tests/persistence/test_asset_store.py
- Test: backend/tests/persistence/test_workspace_migration.py
- Modify only if required by verified integration: existing Task4 domain files; do not alter API or frontend files.

Interfaces:
- Consumes: DraftRecord, ArchivedDish, AssetKind, MediaType, AssetRef, SourceInput and Task4 validation rules.
- Produces: WorkspacePaths.create(root: Path) -> WorkspacePaths, DraftRepository.save(record, expected_revision), ArchiveRepository.add_immutable(record, idempotency_key), FileAssetStore.put(data, metadata) -> AssetRef.

- [x] Step 1: Write failing atomic JSON and recovery tests

Add tests showing that a failed os.replace leaves the old file unchanged, successful writes use canonical JSON formatting, and a valid .bak can recover a damaged main file while an invalid backup is rejected.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_atomic.py -q
~~~
Expected: FAIL because the persistence package and atomic_write_json do not exist.

- [x] Step 2: Implement the minimal atomic JSON helper

Implement atomic_write_json(path: Path, payload: object) -> None and read_json_with_backup(path: Path, validator: Callable[[object], T]) -> T with deterministic UTF-8/LF JSON, same-directory temporary files, flush/fsync, one .bak, os.replace, and validated backup recovery. Keep temporary-file cleanup best-effort and never replace the last valid main file before the new temp file is ready.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_atomic.py -q
~~~
Expected: PASS.

- [x] Step 3: Write failing workspace and migration tests

Cover idempotent directory creation, first-run D<YYYYMMDD> AuthorName persistence, bootstrap contents limited to schemaVersion and workspacePath, staging migration hash/count validation, and retention of the old workspace after a successful switch.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_workspace_migration.py -q
~~~
Expected: FAIL because WorkspacePaths and bootstrap migration helpers do not exist.

- [x] Step 4: Implement workspace paths, records, and migration

Implement WorkspacePaths for the §8 directory tree and a small workspace/bootstrap record boundary. Use local date only for the first persisted author_name; subsequently read the stored value. Migration must copy into target staging, verify file count and SHA-256, atomically update bootstrap, and leave the old directory intact.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_workspace_migration.py -q
~~~
Expected: PASS.

- [x] Step 5: Write failing Repository tests

Cover Draft save/get/list, expected revision conflict, .bak recovery, index rebuild, Archive immutable add, same-key idempotency, different-key collision rejection, delete-to-trash, tombstone creation, and exclusion of deleted records from active results.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_repositories.py -q
~~~
Expected: FAIL because Repository implementations do not exist.

- [x] Step 6: Implement DraftRepository, ArchiveRepository, and trash operations

Store records under the §8 entity paths, validate every read with the corresponding Pydantic model, update indexes only after the entity write succeeds, rebuild missing/corrupt indexes from entity records, enforce optimistic revision checks, preserve immutable archives, move deleted archive directories into trash/cookbook/<dishId>, and persist a tombstone with dishId, deletedAt, and contentHash.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_repositories.py -q
~~~
Expected: PASS.

- [x] Step 7: Write failing Asset Store tests

Cover SHA-256 and byte size, UUID plus two-character sharding, allowed image/ZIP metadata, dimension requirements, duplicate content behavior, rejection of unsupported MIME or extension, path traversal, absolute-path leakage, and reading/statting registered assets.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_asset_store.py -q
~~~
Expected: FAIL because FileAssetStore and metadata validation do not exist.

- [x] Step 8: Implement FileAssetStore

Implement AssetMetadata, FileAssetStore.put, open, and stat using validated AssetRef records and the safe relative-path rules. Write bytes through the atomic helper, calculate lowercase SHA-256 before registration, preserve image dimensions when supplied, and never return an absolute path from the public reference.

Run:
~~~powershell
python -m pytest backend/tests/persistence/test_asset_store.py -q
~~~
Expected: PASS.

- [x] Step 9: Run persistence and domain regression checks

Run:
~~~powershell
python -m pytest backend/tests/persistence -q
python -m pytest backend/tests/domain backend/tests/persistence -q
python -m ruff check backend
python -m mypy backend/src
~~~

Confirm that only test temporary directories receive runtime files, no API Key or absolute asset path appears in serialized public data, and no uv.lock or virtual environment is added.

- [x] Step 10: Complete Session evidence after user acceptance

Update the Task5 Session and STATUS.md with test/review evidence, then stage only the Task5 persistence implementation, tests, and this Session's control-plane documents for one focused commit:

~~~powershell
git add backend/src/pelican_town_specials/persistence backend/tests/persistence AGENTS.md README.md docs/development/README.md docs/development/STATUS.md docs/development/sessions/2026-08-02-task-5-persistence.md docs/superpowers/specs/2026-08-02-task-5-persistence-design.md docs/superpowers/plans/2026-08-02-task-5-persistence.md
git commit -m "feat: add atomic local workspace persistence"
~~~

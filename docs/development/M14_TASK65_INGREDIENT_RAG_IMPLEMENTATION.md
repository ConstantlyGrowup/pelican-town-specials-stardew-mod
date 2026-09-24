# M14 Task65｜本地原料 RAG 实施与资源报告

## 实施边界

Task65 增加了本地、逐项原料候选检索及可验证的静态索引构建。Ask Gus 的普通生产路径仍使用旧 backend；只有内部显式选择 RAG 时才运行新检索器。Task65 不做 JEV 对照、不决定是否启用 RAG，不修改 API、UI、schema、Canonical、Blueprint、试用、Mod 导出或用户数据；不增加 Provider 调用，也不进行整道菜联合选择。

仅在显式 RAG 模式且过滤已用 ID 后仍有结果时，RAG 候选才会在 mapper 前排除本菜已用的目录 ID。RAG 查询失败或无剩余候选时，旧 lexical fallback 保持原样，不做 used-ID 过滤；默认 LEGACY 候选序列也保持原样。未知 ID 和不可用条目不会被静默过滤，仍经过既有 mapper 校验。模型、目录、索引、清单或编码错误只禁用本地 RAG，并由 Ask Gus 接回旧候选路径和原 mapper。日志只记录固定内部原因码，不记录 query 内容。

## 固定来源与离线产物

| 资产 | 来源 / 处理 | 字节数 | SHA-256 |
|---|---|---:|---|
| E5 源 ONNX | `intfloat/multilingual-e5-small`，官方 revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`，`onnx/model.onnx` | 470,268,510 | `CA456C06B3A9505DDFD9131408916DD79290368331E7D76BB621F1CBA6BC8665` |
| CPU 量化 ONNX | ONNX Runtime dynamic QInt8、per-channel；量化 `MatMul` 与 `Gather` | 118,308,811 | `739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717` |
| SentencePiece tokenizer | 同一官方 revision 的 `sentencepiece.bpe.model` | 5,069,051 | `CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865` |
| 有序向量 | 原版目录 253 行 × 384 维、little-endian float32 | 388,608 | `D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58` |
| 严格 manifest | 固定 catalog/model/tokenizer/vector hashes、版本、shape、量化和 tokenizer 配置 | 4,201 | 由 bundle smoke 校验清单字段与对应资产 hash |

官方 `tokenizer.json` 仅作构建时 parity reference，不进入生产包：17,082,730 bytes，SHA-256 `0B44A9D7B51C3C62626640CDA0E2C2F70FDACDC25BBBD68038369D14EBDF4C39`。目录输入 SHA-256 为 `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`，符合 `stardew-1.6.15-v1` 和 253 个合格条目。

构建脚本核对 Task64 fixture 的固定 hash，并逐项比较官方 fast tokenizer 与生产 SentencePiece 编码：253 条目录 passage、50 个 distinct normalized Task64 query、5 个边界样例（NFKC/空白归一、大小写/重音、中日韩文本和 128-token 截断）共 **308/308 完全相同**。另有含 `<s>`, `</s>`, `<unk>`, `<pad>`, `<mask>` 的控制 token 字面量样例：SentencePiece 对这类 AddedToken 输入与 reference 不等价；运行时明确以非敏感原因码 `rag_tokenizer_input_unsupported` 禁用 RAG，让旧 mapper 接管。测试覆盖这些五种字面量。上述 parity 结果只适用于已核验样本，不宣称对任意文本完全等价。

SentencePiece 普通词表 token ID 按固定 XLM-R 对照映射 `SP ID + 1`；unk、BOS、EOS 分别映射到 reference ID 3、0、2。每条输入加 BOS/EOS，内容最多保留 126 tokens，总长上限 128。推理一次处理一个 query，不做 padding，attention mask 全为 1；若模型暴露 `token_type_ids` 则传全 0。无需运行时下载或远端 embedding。

构建依赖固定为 ONNX Runtime 1.26.0、ONNX 1.21.0、NumPy 2.5.2、SentencePiece 0.2.2；仅 parity/build 阶段使用 Tokenizers 0.23.2 与 Hugging Face Hub 1.29.0。生产包使用 ONNX Runtime CPU 与 SentencePiece，不打包 ONNX、Tokenizers、Torch、Transformers、SciPy、scikit-learn 或 Hub 客户端。来源与许可证：E5 模型 MIT（[官方固定 revision](https://huggingface.co/intfloat/multilingual-e5-small/tree/fd1525a9fd15316a2d503bf26ab031a61d056e98)）；SentencePiece Apache-2.0（[官方项目许可证](https://github.com/google/sentencepiece/blob/master/LICENSE)）；ONNX Runtime MIT（[官方许可证](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)）；NumPy BSD-3-Clause（[官方许可证](https://github.com/numpy/numpy/blob/main/LICENSE.txt)）；build-only Tokenizers Apache-2.0（[官方许可证](https://github.com/huggingface/tokenizers/blob/main/LICENSE)）。对应 notice 已更新于 `packaging/release/THIRD_PARTY_NOTICES.txt`。

可复现产物默认输出在 ignored 路径 `output/m14-task65/ingredient-rag-spm/`。执行时固定 revision 的模型文件已在本机 cache；设 `HF_HUB_OFFLINE=1` 后构建仍完成，parity 与产物 hashes 均通过。ORT 输出了“建议在量化前 preprocessing”的提示；本实现按冻结配置使用动态量化，没有额外校准集或在线步骤。

## 实测资源与 Windows 包

测试机器为 Windows 11 10.0.26200、Python 3.13.7、Intel Core Ultra 9 275HX（24 logical processors）、约 32 GiB RAM。20 个顺序独立 Python 进程均从本地 catalog、bundle 资源启动，并在首次 RAG retrieval 中惰性加载 ONNX、SentencePiece、manifest 和 flat index。每次的 Top 5 ID 一致：

| 指标 | 中位数 | 最大值 | Task65 限值 |
|---|---:|---:|---:|
| 首次 retrieval（包含惰性模型/索引加载、import 与 query） | 1,178.337 ms | 1,466.078 ms | 5,000 ms |
| 首次 retrieval 后进程 RSS | 230.170 MiB | 230.617 MiB | 256 MiB |
| 首次 retrieval 相对 app/catalog imports 的 RSS 增量 | 188.348 MiB | 188.602 MiB | 256 MiB |

另以 50 个 normalized Task64 query 各重复 10 次，共 500 次暖态完整检索，nearest-rank p95 为 **8.449 ms**（限值 100 ms）；三个并发 query 总计 16.156 ms。单独组件检查也确认运行 provider 为 `CPUExecutionProvider`。暖态 query 与测量中的 20 次冷加载均无网络访问。

Windows onedir build 使用隔离目标 `output/m14-task65/bundle-sentencepiece-r2/PelicanTownSpecials-windows-x64/`，没有覆盖预存的 `dist/PelicanTownSpecials-windows-x64/`。预存 dist 为 115,177,433 bytes（109.84 MiB）；新 onedir 为 276,484,585 bytes（263.68 MiB），本机两包观察到的总大小增量为 161,307,152 bytes（153.84 MiB）。另外按新增文件树逐项计量：RAG 模型/tokenizer/index/manifest 为 123,770,671 bytes，ONNX Runtime 文件树为 34,259,448 bytes，SentencePiece 文件树为 1,459,712 bytes，合计 **159,489,831 bytes（152.10 MiB）**，低于新增发行内容 180 MiB 限值。预存 dist 是既有本机包，不保证与本次构建完全同条件；新增文件树和本次 bundle 总字节数一并列出供 detector 独立核对。

bundle 中未发现 `torch`、`transformers`、`sentence_transformers`、`scipy`、`sklearn`、`onnx`、`tokenizers`、`huggingface_hub` 或 `datasets` 的文件路径。第一次 PyInstaller 分析在共享开发环境中发现这些 evaluation-only hook；因此 spec 显式排除非 runtime 评测/构建包，第二次完整 build 后扫描为 0 个匹配文件。生产 onedir 仅加入固定四个 RAG 数据资产及 CPU runtime 依赖。

`smoke_windows_bundle.ps1` 离线核对了四项资产 hash、manifest revision/catalog/model/tokenizer/vector contract、递归 `_sqlite3` 扩展、exe、静态首页，并成功做两次干净启动、health/homepage 请求和同一非空 Canonical registry 重开。该应用 smoke 因产品默认 backend 仍为 legacy，不会主动触发 RAG 推理；20-process inference/RSS runner 从本地 bundle 资源路径加载模型、tokenizer、manifest 和向量，运行于宿主 Python 中固定版本的 ONNX Runtime/SentencePiece/NumPy，而非已冻结 exe 进程。没有据此声称 exe 普通用户默认路径已切至 RAG。

## 验证记录

- Task65 focused pytest（RAG、Ask Gus、三槽并发）：**58 passed**。
- Windows `build_windows.ps1` 全量门禁：backend **999 passed, 2 skipped**；frontend **231 passed**；TypeScript/Vite build、OpenAPI drift、ignored-path policy、telemetry dashboard contract 与 model/index rebuild 成功。backend 有 3 条重复 ZIP entry 测试预期 warning；前端构建有一个 >500 kB chunk advisory。
- isolated Windows PyInstaller onedir、exe icon/version gate、release-content gate：成功；offline bundle smoke：成功。
- Ruff scoped check：通过；mypy scoped check：9 files 无问题；`git diff --check`：通过（仅有现存 LF/CRLF 提示）。

### Detector revise round 1 修复证据

- 修正候选兼容边界：成功且去重后非空的 RAG 结果在 mapper 前排除本菜已用 ID；RAG 故障或无剩余结果时返回未过滤的旧 lexical 候选。LEGACY 对 `egg` 仍返回 catalog 原始 Top 5 序列。回归测试确认默认 `core_fixture` 映射仍为 `176, 399`，RAG 正常候选仍去重，失败回退包含旧序列中的 `176`。
- Release clean-runner 闭包：新增独立 `build` dependency group，精确固定 `huggingface-hub==1.29.0`、`onnx==1.21.0`、`tokenizers==0.23.2`；可复用 `build.yml` 在开发组与 editable 项目安装时一并安装此组。此前一步会先升级 pip；[官方 pip 文档](https://pip.pypa.io/en/stable/user_guide/#dependency-groups)说明 `--group` 从 pip 25.1 开始支持，且可重复指定。该 build 组不进入产品 runtime dependencies，PyInstaller spec 显式排除对应三个模块。
- 确定性配置/打包契约测试检查 dependency group 固定版本、Release workflow 安装命令、runtime dependencies 未引入 build 包及 spec excludes。没有在本轮启动 GitHub clean runner，也没有重新执行 Windows onedir build；上节包体和 smoke 数据仍是修复前的独立构建证据，不作为本轮 clean-runner 或重建通过声明。
- 修复轮 scoped pytest：`backend/tests/ingredient_rag`、Ask Gus 与三槽并发合计 **62 passed**；最后 candidate/fallback 配置与重复 Egg 映射的 7 项定向回归 **7 passed**。本轮 `ruff check` 通过；`mypy backend/src` 为 **105 files 无问题**。额外 `ruff format --check` 初始同时标记两份共享 Task65 大文件与新 build 契约测试；新契约测试现已单独格式化并通过其 format check，剩余全文件检查仍标记 `orchestrator.py` / `test_ask_gus.py`，没有对这两份共享大文件做整体重排，以免带入本轮之外的格式改写。

## 限制和状态

本报告只记录 Task65 实施和证据，不给 RAG 与旧方案的语义质量优劣结论；质量结论、菜品全合理率对照以及是否改变默认选择留给 Task66。旧 backend 保持普通生产默认。本 worker 未编辑 Session/STATUS，未运行 JEV，未提交、push 或发布。Windows exe smoke 未激活内部 RAG selector；报告的推理测量来自相同 pinned assets 和同版本宿主 runtime 的独立 fresh-process runner。

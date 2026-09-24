# M14 Task 63｜本地原料 RAG 选型摘要

| 字段 | 值 |
|---|---|
| 合同 | `m14-task63-local-ingredient-rag-design-v1` |
| 状态 | 设计完成；通过 Task64–66 资源与质量验证后才可作为默认产品链路 |
| 正式设计 | [`M14_INGREDIENT_RAG_TECHNICAL_DESIGN.md`](../architecture/M14_INGREDIENT_RAG_TECHNICAL_DESIGN.md) |

## 冻结决策

- 只改 Ask Gus 现实语义原料到游戏目录候选这段。模型上游语义错误不属于召回能修复的问题；Canonical 与 Blueprint 路径不变。
- 选择 `intfloat/multilingual-e5-small` 作为本地双语候选，使用通用 CPU ONNX 动态 INT8。发行前固定 40 位模型 revision 和所有资源 SHA-256；运行时不联网。
- 官方 E5 仓库标注 118 MB 的 `model_qint8_avx512_vnni.onnx` 明确依赖 AVX512 VNNI，不作为通用 Windows 包。通用动态量化权重约 118 MB 是比例估算，尚未构建或测量。
- 一个可用原版目录物品就是一个检索单元。精确名称/已核验别名先行，其余使用本地向量精确 Top 5；随后 mapper 仍验证目录 ID/可用性，并在映射前排除已用 ID。食用度不再重排 RAG 候选；鱼类守卫保持在映射之后。
- 253×384 FP32 索引矩阵为 388,608 bytes（379.5 KiB）；随程序打包 flat 文件和 manifest，进程内 exact scan。无向量 DB、ANN、独立服务或用户工作区迁移。
- 模型与索引惰性加载并在进程内复用。缺失、hash/版本不符、CPU 模型加载或推理失败时自动回到现有 Top5 lexical + mapper 旧链路；只留不含 Query 文本的本地原因码。

## Task65/66 采用门槛

| 门槛 | 数值/要求 | 证据状态 |
|---|---:|---|
| 新增发行文件总量 | ≤180 MiB | Task65 packaged Windows build 实测 |
| 首次模型加载 | ≤5 s | Task65 新进程实测；应用 UI 启动不等待模型 |
| 活跃模型额外 RSS | ≤256 MiB | Task65 冷进程测量，至少 20 次 |
| 暖查询 | p95 ≤100 ms | 包含 tokenize/Embedding/253 条扫描；分项记录 |
| 目录向量索引 | ≤0.5 MiB | 计算上限 379.5 KiB，Task65 核验文件 |
| 同集质量（Task63 原定口径） | Recall@5 不低于旧链路；非兜底合理率严格高于旧链路，覆盖数不更差 | Task66 用 Task64 冻结 Query 与盲化 JEV 评测；此行质量主指标已被后续用户修订覆盖，见下方补记 |

2026-09-23 用户在 Task64 基线完成后，将 Task66 主指标明确改为固定菜品集合的“全部原料合理率”，并确认保持逐项召回，不加入整菜联合选择。Task63 原设计的逐项合理率保留为辅助指标；Task64 历史结果不改写。现行质量门槛见 ignored `M14_INGREDIENT_RAG_TECHNICAL_DESIGN.md` v1.1 与 M14 计划 v1.4。

任一资源门槛未过，或同集没有质量改善，RAG 不设为发行默认；Task65 保留现有链路且记录原因。以上性能和质量都是未来门槛，不能写成已实测结果。M12 的 `paraphrase-multilingual-MiniLM-L12-v2` 数据只作 CPU 资源参照，其 Canonical 命中率不代表原料结果。

## 资源参照与边界

M12 对 MiniLM 记录模型文件 499,557,407 bytes（476.42 MiB）、fresh-process load 21.463 秒、RSS 增量 755.828 MiB、700 次 query 编码含在内的平均召回 14.3037 ms。其 Canonical 集命中为 52/60，Current 为 59/60；这些数值不预测 E5 的资源，也不构成 M14 原料质量对照。

设计依据：E5 官方模型卡和[官方文件目录](https://huggingface.co/intfloat/multilingual-e5-small/tree/main/onnx)，[ONNX Runtime 动态量化说明](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)，MiniLM[官方模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)，以及本地 M12 结果文件。实现前应以固定 revision 和实际 Windows 包重新核对文件、依赖、许可证、CPU 兼容性、内存和冷加载。

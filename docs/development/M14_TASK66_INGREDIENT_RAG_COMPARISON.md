# M14 Task66 — Ingredient RAG Same-Set Comparison

- Acceptance contract: `m14-task66-ingredient-rag-comparison-v1`
- Generated: `2026-09-23T13:45:26.057327+00:00`
- Frozen set: 24 dishes / 72 query occurrences; fixture SHA-256 `7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7`; catalog `stardew-1.6.15-v1` SHA-256 `4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B`.
- Task64 raw artifacts were read-only and their hashes were rechecked unchanged after evaluation. Task66 raw outputs are ignored under `output/m14-task66/`.

## Result

The primary fixed-denominator dish all-reasonable rate changed from **14/24 (58.33%)** to **18/24 (75.00%)**. With the same returned JEV model on both sides, the paired set has **4 improved, 0 regressed, and 20 unchanged dishes**.

The frozen adoption gate is **met**: the primary numerator is strictly higher, Recall@5 and reasonable coverage did not fall, and the Task65 resource budget evidence passes. This is evaluation evidence only; the product default remains `LEGACY`, and no default change is authorized by this Task.

| Metric | Task64 legacy | Task66 RAG + mapper |
|---|---:|---:|
| Dish all-reasonable (fixed 24) | 14/24 (58.33%) | 18/24 (75.00%) |
| Non-fallback item reasonable (determinate only) | 61/71 (85.92%) | 65/72 (90.28%) |
| Reasonable coverage of fixed 72 | 61/72 (84.72%) | 65/72 (90.28%) |
| Gold Recall@5 (mean per occurrence) | 70/72 (97.22%) | 72/72 (100.00%) |
| At least one acceptable Gold in Top 5 | 70/72 | 72/72 |
| Final selection in acceptable Gold | 60/72 | 66/72 |
| Candidate retrieval misses / selection misses after hit | 2 / 10 | 0 / 6 |
| Mapping failures / catalog fallback | 0 / 1 | 0 / 0 |
| JEV choice counts (reasonable / unreasonable / undecidable) | 61 / 10 / 0 | 65 / 7 / 0 |

## Paired dish outcomes

| Dish | Legacy all reasonable | RAG all reasonable | Transition |
|---|:---:|:---:|---|
| `d01` Tomato and egg stir-fry | yes | yes | unchanged |
| `d02` Carp rice bowl | no | no | unchanged |
| `d03` Cherry tomato mushroom omelet | no | no | unchanged |
| `d04` Salmon with potatoes | yes | yes | unchanged |
| `d05` Blueberry pancakes | no | no | unchanged |
| `d06` Cranberry rice pudding | no | yes | improved |
| `d07` Salmon rice bowl | yes | yes | unchanged |
| `d08` Eel rice bowl | no | yes | improved |
| `d09` Aubergine tomato stew | no | yes | improved |
| `d10` Mushroom leek soup | yes | yes | unchanged |
| `d11` Cauliflower cheese bake | yes | yes | unchanged |
| `d12` Strawberry milkshake | yes | yes | unchanged |
| `d13` Apple tart | no | no | unchanged |
| `d14` Eel and ginger soup | yes | yes | unchanged |
| `d15` Fiddlehead risotto | no | yes | improved |
| `d16` Corn chowder | yes | yes | unchanged |
| `d17` Salmonberry tart | no | no | unchanged |
| `d18` Artichoke cheese dip | yes | yes | unchanged |
| `d19` Rainbow trout with kale | yes | yes | unchanged |
| `d20` Tuna cabbage wraps | no | no | unchanged |
| `d21` Parsnip soup | yes | yes | unchanged |
| `d22` Peach and orange fruit salad | yes | yes | unchanged |
| `d23` Pineapple pepper stir-fry | yes | yes | unchanged |
| `d24` Leek and potato soup | yes | yes | unchanged |

## JEV protocol, reuse, and cost

Returned model/provider: `typesafe/jev-1.13-20260917` / `TypeSafe`. Task64 and Task66 versions match exactly. There are **72/72** new-side typed judgments: **64** exact-state Task64 completed typed decisions reused and **8** Task66 provider calls succeeded (one protocol probe plus additional calls). No 429, failed, missing, undecidable, or not-attempted JEV outcomes occurred.
Incremental Task66 reported provider usage cost: **$0.000187152**. Task64 usage attached to reused provenance is **$0.001501500** and is not included in incremental Task66 cost. The total call ceiling was 72; actual provider calls were 8.

The blind JEV state contained only dish context, the semantic ingredient, and the final mapped catalog object. Gold IDs, Top-5 candidates/scores, and old/new labels were not sent. For reused judgments, exact request-state equality, returned model, typed choice, source query ID, and Task64 `jev.jsonl` hash are recorded in `metrics.json` `task64_reuse_provenance`; the copied response data remains in ignored Task66 `jev.jsonl`.

## Retrieval timing and resource gate

Task64 `elapsed_ms` covers candidate building plus mapping; Task66 `total_elapsed_ms` covers candidate selection (including RAG retrieval) plus mapping, so these are comparable end-to-end per-item timings. The frozen Task64 artifact does not split retrieval and mapping phases. Task66 also records RAG retrieval-only and mapper-only timings; its sequence includes the first cold lazy-load request.

| Comparable per-item mapping pipeline | Task64 legacy | Task66 RAG |
|---|---:|---:|
| Candidate building + mapping median | 1.098 ms | 6.259 ms |
| p95 (nearest-rank) | 1.846 ms | 7.924 ms |
| Maximum | 2.150 ms | 1639.913 ms |

| Task66 phase timing | Median | p95 (nearest-rank) | Maximum |
|---|---:|---:|---:|
| RAG retrieval only | 6.221 ms | 7.867 ms | 1639.760 ms |
| Mapper only | 0.031 ms | 0.052 ms | 0.128 ms |

Task66 RAG retrieval state was success for 72/72 items, with 0 degraded retrievals. RAG asset manifest SHA-256: `93E9AED32AA68DEC48D1C6E102C4F82FABDB916B84CD852E807F85BF3284DE85`; E5 revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`. Pinned asset SHA-256 — ONNX model `739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717`, tokenizer `CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865`, vector index `D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58`.

| Task65 measured resource | Observed | Limit | Gate |
|---|---:|---:|:---:|
| Vector asset | 388,608 bytes | 524,288 bytes | pass |
| Added distribution | 159,489,831 bytes | 188,743,680 bytes | pass |
| Cold retrieval max | 1466.078 ms | 5000.000 ms | pass |
| Model RSS delta max | 188.602 MiB | 256.000 MiB | pass |
| Warm query p95 | 8.449 ms | 100.000 ms | pass |

Resource values are the frozen Task65 measurements, not remeasured in Task66. Task65's Windows bundle smoke did not select the RAG backend because production default remains LEGACY; Task66 RAG evaluation used the actual explicit RAG selector and mapper in host Python with the pinned assets. No claim is made about end-user causal impact or default-path EXE quality.

## Failures and limitations

mapping_failures: 0; fallbacks: 0; retrieval_degraded: 0; JEV call failures: 0; JEV missing: 0; JEV undecidable: 0; JEV not attempted: 0.
The sample is a curated fixed 24-dish / 72-occurrence set with multi-ID Gold labels, not natural user traffic. Gold agreement is retrieval evidence, not semantic ground truth. No query/label/top-K/alias/mapper tuning was performed. Historical Task64 outputs remain read-only. No provider/UI/API/schema/default changes were made.

Raw RAG JSONL SHA-256: `77E7DC7627544EB032856891B2C673DAC8666880D7F58E24039DEE257F53DC0E`. Task66 JEV JSONL SHA-256: `A94DFCDDD7F5B64C7D1587D327E42A3300FB4921F235053CCF9722A22B61F603`. Metrics SHA-256: `81E98D113AF5493033611F84DCB7A460B4545CF6560DB85C5AE8BA804C576D6F`. Raw paths: `output/m14-task66/rag_results.jsonl`, `output/m14-task66/jev.jsonl`, `output/m14-task66/metrics.json`, and `output/m14-task66/manifest.json` (all ignored).

## Per-item outcomes

`Top5` lists only local RAG candidate IDs (ordered); JEV receives neither those IDs nor their scores. Old/new choices are catalog IDs. `source/status` records the actual RAG retrieval result.

| Query | Input | Legacy ID / JEV | RAG Top5 IDs | RAG ID / JEV | RAG source/status |
|---|---|---|---|---|---|
| `d01-i01` | 西红柿 | 256 / reasonable | 256, Broccoli, 192, 266, 230 | 256 / reasonable | rag / success |
| `d01-i02` | egg | 176 / reasonable | 176, 180, 272, 231, 174 | 176 / reasonable | rag / success |
| `d01-i03` | garlic | 248 / reasonable | 248, 772, 921, 245, 226 | 248 / reasonable | rag / success |
| `d02-i01` | Carp | 209 / reasonable | 142, 209, 269, 682, 901 | 142 / reasonable | rag / success |
| `d02-i02` | white rice | 232 / unreasonable | 157, 232, 271, 423, 905 | 157 / unreasonable | rag / success |
| `d02-i03` | green onion | 153 / unreasonable | 153, 188, 399, 614, 20 | 153 / unreasonable | rag / success |
| `d03-i01` | cherry tomatoes | 638 / unreasonable | 638, 256, 907, 192, 264 | 638 / unreasonable | rag / success |
| `d03-i02` | button mushroom | 205 / reasonable | 205, 404, 422, 265, 921 | 205 / reasonable | rag / success |
| `d03-i03` | egg | 176 / reasonable | 176, 180, 272, 231, 174 | 176 / reasonable | rag / success |
| `d04-i01` | salmon | 139 / reasonable | 139, 296, 212, 795, 796 | 139 / reasonable | rag / success |
| `d04-i02` | potato | 192 / reasonable | 192, 649, 210, 256, 246 | 192 / reasonable | rag / success |
| `d04-i03` | cooking oil | 247 / reasonable | 247, 432, 772, 242, 196 | 247 / reasonable | rag / success |
| `d05-i01` | blueberry | 258 / reasonable | 258, 234, 410, 238, 296 | 258 / reasonable | rag / success |
| `d05-i02` | wheat flour | 246 / unreasonable | 246, 197, 240, 200, 606 | 246 / unreasonable | rag / success |
| `d05-i03` | egg | 176 / reasonable | 176, 180, 272, 231, 174 | 176 / reasonable | rag / success |
| `d06-i01` | cranberries | 282 / reasonable | 282, 238, 612, 732, 270 | 282 / reasonable | rag / success |
| `d06-i02` | rice | 232 / unreasonable | 423, 232, 271, 905, 812 | 423 / reasonable | rag / success |
| `d06-i03` | milk | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |
| `d07-i01` | 鲑鱼 | 139 / reasonable | 139, 212, 795, 164, 796 | 139 / reasonable | rag / success |
| `d07-i02` | 大米 | 423 / reasonable | 423, 232, 271, 246, 905 | 423 / reasonable | rag / success |
| `d07-i03` | ginger | 829 / reasonable | 829, 903, 419, 348, 245 | 829 / reasonable | rag / success |
| `d08-i01` | eel | 148 / reasonable | 148, 162, 225, 226, 176 | 148 / reasonable | rag / success |
| `d08-i02` | rice | 232 / unreasonable | 423, 232, 271, 905, 812 | 423 / reasonable | rag / success |
| `d08-i03` | 大葱 | 399 / reasonable | 399, 635, 20, 235, 22 | 399 / reasonable | rag / success |
| `d09-i01` | aubergine | 176 / — | 272, 231, 208, 634, 306 | 272 / reasonable | rag / success |
| `d09-i02` | tomato | 256 / reasonable | 256, 192, 218, 457, 456 | 256 / reasonable | rag / success |
| `d09-i03` | garlic | 248 / reasonable | 248, 772, 921, 245, 226 | 248 / reasonable | rag / success |
| `d10-i01` | mushroom | 205 / reasonable | 205, 404, 422, 208, 30 | 205 / reasonable | rag / success |
| `d10-i02` | 韭葱 | 20 / reasonable | 20, 399, Powdermelon, 635, 239 | 20 / reasonable | rag / success |
| `d10-i03` | 牛奶 | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |
| `d11-i01` | cauliflower | 190 / reasonable | 190, 197, 421, 259, 250 | 190 / reasonable | rag / success |
| `d11-i02` | cheese | 424 / reasonable | 424, 197, 426, 239, 348 | 424 / reasonable | rag / success |
| `d11-i03` | milk | 184 / reasonable | 184, 186, 436, 438, 246 | 184 / reasonable | rag / success |
| `d12-i01` | 草莓 | 400 / reasonable | 400, 595, 90, 731, 155 | 400 / reasonable | rag / success |
| `d12-i02` | milk | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |
| `d12-i03` | sugar | 245 / reasonable | 245, 724, MysticSyrup, 731, 350 | 245 / reasonable | rag / success |
| `d13-i01` | 苹果 | 613 / reasonable | 613, 233, 350, 410, 832 | 613 / reasonable | rag / success |
| `d13-i02` | egg | 176 / reasonable | 176, 180, 272, 231, 174 | 176 / reasonable | rag / success |
| `d13-i03` | wheat flour | 246 / unreasonable | 246, 197, 240, 200, 606 | 246 / unreasonable | rag / success |
| `d14-i01` | eel | 148 / reasonable | 148, 162, 225, 226, 176 | 148 / reasonable | rag / success |
| `d14-i02` | 姜 | 829 / reasonable | 829, 903, 419, 280, 412 | 829 / reasonable | rag / success |
| `d14-i03` | 韭葱 | 20 / reasonable | 20, 399, Powdermelon, 635, 239 | 20 / reasonable | rag / success |
| `d15-i01` | 蕨菜 | 259 / reasonable | 259, 649, 197, 190, 278 | 259 / reasonable | rag / success |
| `d15-i02` | rice | 232 / unreasonable | 423, 232, 271, 905, 812 | 423 / reasonable | rag / success |
| `d15-i03` | cheese | 424 / reasonable | 424, 197, 426, 239, 348 | 424 / reasonable | rag / success |
| `d16-i01` | 玉米 | 270 / reasonable | 270, 834, 851, 423, Raisins | 270 / reasonable | rag / success |
| `d16-i02` | 牛奶 | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |
| `d16-i03` | potato | 192 / reasonable | 192, 649, 210, 256, 246 | 192 / reasonable | rag / success |
| `d17-i01` | 美洲大树莓 | 296 / reasonable | 296, 258, 423, 400, 410 | 296 / reasonable | rag / success |
| `d17-i02` | wheat flour | 246 / unreasonable | 246, 197, 240, 200, 606 | 246 / unreasonable | rag / success |
| `d17-i03` | egg | 176 / reasonable | 176, 180, 272, 231, 174 | 176 / reasonable | rag / success |
| `d18-i01` | 洋蓟 | 274 / reasonable | 274, 605, 152, 259, 727 | 274 / reasonable | rag / success |
| `d18-i02` | cheese | 424 / reasonable | 424, 197, 426, 239, 348 | 424 / reasonable | rag / success |
| `d18-i03` | 蒜 | 248 / reasonable | 248, 772, Raisins, 250, 148 | 248 / reasonable | rag / success |
| `d19-i01` | 虹鳟鱼 | 138 / reasonable | 138, 701, 699, 837, 146 | 138 / reasonable | rag / success |
| `d19-i02` | 甘蓝菜 | 250 / reasonable | 250, 190, 197, Broccoli, 278 | 250 / reasonable | rag / success |
| `d19-i03` | 油 | 772 / reasonable | 247, 772, 281, 432, 424 | 247 / reasonable | rag / success |
| `d20-i01` | 金枪鱼 | 130 / reasonable | 130, 136, 137, 837, 800 | 130 / reasonable | rag / success |
| `d20-i02` | 红叶卷心菜 | 266 / reasonable | 266, 648, 230, 213, 195 | 266 / reasonable | rag / success |
| `d20-i03` | chili pepper | 215 / unreasonable | 215, 260, 264, 608, 637 | 215 / unreasonable | rag / success |
| `d21-i01` | 防风草 | 24 / reasonable | 24, 199, 272, 152, 30 | 24 / reasonable | rag / success |
| `d21-i02` | milk | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |
| `d21-i03` | garlic | 248 / reasonable | 248, 772, 921, 245, 226 | 248 / reasonable | rag / success |
| `d22-i01` | peach | 636 / reasonable | 636, 141, 402, 836, 457 | 636 / reasonable | rag / success |
| `d22-i02` | orange | 635 / reasonable | 635, 399, 398, 270, 812 | 635 / reasonable | rag / success |
| `d22-i03` | strawberry | 400 / reasonable | 400, 612, 234, 238, 296 | 400 / reasonable | rag / success |
| `d23-i01` | 菠萝 | 832 / reasonable | 832, 422, 812, 807, 264 | 832 / reasonable | rag / success |
| `d23-i02` | hot pepper | 260 / reasonable | 260, 215, 207, 907, 201 | 260 / reasonable | rag / success |
| `d23-i03` | ginger | 829 / reasonable | 829, 903, 419, 348, 245 | 829 / reasonable | rag / success |
| `d24-i01` | 韭葱 | 20 / reasonable | 20, 399, Powdermelon, 635, 239 | 20 / reasonable | rag / success |
| `d24-i02` | 土豆 | 192 / reasonable | 192, 188, 402, 218, 239 | 192 / reasonable | rag / success |
| `d24-i03` | 牛奶 | 184 / reasonable | 184, 186, 436, 438, 424 | 184 / reasonable | rag / success |

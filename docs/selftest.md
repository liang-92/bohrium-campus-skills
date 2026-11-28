# 自测记录：三个自建案例 + 引擎降级对照（2026-11-23）

与 `docs/audit-2026-11-23.md` 的平台侧审计互补：本文是**本地自建测试用例**的完整
实测记录。测试用例按平台 case 约定构造（`case.json` + `task.md` + `*.pdf`），
但不随仓库分发 PDF；复现命令见文末，用任意同类论文即可重跑。

## 测试用例

| 用例 | 材料 | 考察点 |
|---|---|---|
| `case-single` | arXiv 单栏论文（1706.03762v7, Attention） | 章节树、块锚点、表格/公式/参考文献覆盖 |
| `case-twocol` | ACL 双栏论文（acl2020.papers.proc-1.pdf） | 多栏阅读顺序、串栏拼接修正 |
| `case-broken` | 故意损坏的 PDF（随机字节，无 xref/trailer） | 异常识别与诚实状态上报 |
| `case-single` × paper-refs | 同上单栏论文 | 第二个 Skill 的引用抽取链路 |

## 结果（pymupdf 引擎，与本仓库 bench 基准逐项一致）

| 用例 | 页 | 块 | 表格 | 公式 | 参考文献 | 阅读顺序倒挂 | verify.py | 状态 |
|---|---|---|---|---|---|---|---|---|
| case-single | 15 | 213 | 4 | 5 | 40 | **0** | 通过 | complete |
| case-twocol | 6 | 156 | 3 | 1 | 47 | **0** | 通过 | complete |

paper-refs 对 case-single：40 条引用证据、`output_contract` 9 字段全填充、status=complete。

**损坏 PDF（case-broken）**：`status=unable`，uncertainty 明确记录
`FileDataError: Failed to open file ... as type pdf`，不生成文档结构。
这验证了「读不出来就如实标注，而不是靠猜补齐」的失败可见原则。

## 引擎降级对照（重要发现与修复）

同一份 case-single，卸载 PyMuPDF 后自动降级到 pypdf 后端：

| 指标 | pymupdf | pypdf（降级） |
|---|---|---|
| blocks | 268 | 78 |
| tables | 4 | **0** |
| references | 41 | **0** |
| status | complete | partial（本次修复后自动封顶） |

**修复**：`run.py` 现在把引擎降级写进 `result.json` 顶层——
`run.engine` / `run.degraded_engine` 字段 + uncertainty 说明 +
`complete` 自动降为 `partial`。此前降级信息只在 run.log 里，读 result.json
的评分方完全看不到质量折损。

```json
"run": {"engine": "pypdf 7.1.1", "degraded_engine": true, ...}
```

**部署提示**：平台镜像是否预装 `pymupdf` 直接决定解析质量档位
（`environment/resources.yaml` 将其列为 optional）。提交前务必在平台真实
环境跑一次案例，确认 `run.engine` 以 `pymupdf` 开头；否则所有解析类题型的
表格/参考文献得分都会受限。

## 复现

```bash
# 构造用例目录（case.json/task.md 按 skills/*/examples/case.example.json 的接口）
mkdir -p case-single && cp <任一arXiv单栏PDF> case-single/paper.pdf

# 正常路径
python3 skills/paper-parse/scripts/run.py --input case-single --out out
python3 skills/paper-parse/scripts/verify.py --out out --kind generic

# 降级路径（临时卸载主力引擎）
python3 -m pip uninstall -y pymupdf
python3 skills/paper-parse/scripts/run.py --input case-single --out out-degraded
# 确认 out-degraded/result.json: run.degraded_engine == true 且 status == partial
python3 -m pip install pymupdf
```

---

## 第二轮：带标准答案的合成用例（`_test/cases/`）

上面三个用例用的是真实论文，只能看“合不合理”；第二轮补上**答案已知**的合成用例，
才能验证“抽得对不对”。

用例由 `_test/cases/make_cases.py` 用 PyMuPDF **现场生成**，所以页面数、作者、表格行列、
数值、公式编号、引用缺口全部在生成时就确定，写进各用例的 `gold.json`。

```bash
cd _test/cases
python make_cases.py          # 生成 18 个用例目录（case.json + task.md + paper.pdf + gold.json）
python run_cases.py           # 逐用例跑对应 Skill，按 gold 逐项核对
python run_matrix.py          # 10 包 × 2 篇真实论文 + verify.py 回归
```

结果（本轮）：

| 项目 | 结果 |
|---|---|
| 自建用例 | **18/18 通过，44/44 断言** |
| 异常用例 | 6/6 均为 `status=unable` 且写出 `result.json`（加密 / 整页图片 / 损坏 / 无 PDF / 零页 / 图片型表格） |
| 十包 × 两篇真论文 | 20/20 成功，`verify.py` 全通过（translate 记 `pending`） |
| 生成物 | `report.md` / `report.json` / `matrix.md` / `matrix.json` |

合成论文里刻意埋的可判分点：

- 作者行下方紧跟机构行（`Institute of Computational Linguistics, Zurich`）——专治“把机构当人名”
- 表格**只有横线没有竖线**，且数值带小数（`24.1` / `4.92` / `0.512`）——专治“小数被拆/行重复”
- 公式编号 `(1)` 被放在行首——专治“编号在行首就检不到”
- 超参齐全但**随机种子故意不报告**——正确行为是进 `missing`，不是补 `42`
- 正文引 `[5]` 但列表只有 `[1]–[4]`；`[4]` 从未被引用；`[2]` 与 `[4]` DOI 相同
- 双栏用例把**右栏先写进内容流**——朴素读取会让右栏跑到左栏前面

`--fill` 往返也实测过：

```
# 译一段 → 只填 2/9 段：status 仍 partial，run.fill = {applied:2, untranslated:7}
# intro 五段全填：draft.status: to_be_written → written，整体 status: partial → complete
```

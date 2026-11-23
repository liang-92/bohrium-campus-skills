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
| case-single | 15 | 268 | 4 | 7 | 41 | **0** | 通过 | complete |
| case-twocol | 6 | 174 | 3 | 0 | 23 | **0** | 通过 | complete |

paper-refs 对 case-single：41 条引用证据、`output_contract` 9 字段全填充、status=complete。

**损坏 PDF（case-broken）**：`status=unable`，uncertainty 明确记录
`FileDataError: Failed to open file ... as type pdf`，不伪造文档结构。
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

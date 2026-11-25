# 本地 50 用例评测：改造结果

仓库：`D:\github\2026-11-23-19-19-35`（仅本地修改，未推送远端）

## 一、四个核心改造

1. 文本输入通道：新增 `core/paperkit/textdoc.py`，把 md、txt、docx、tex、bib、csv、json 转成与 PDF 相同的 document 模型；`sources.discover()` 增加 `primary_text`，`document.analyze()` 在无 PDF 时走文本分支。
2. 契约适配：`contract.stage()` 识别 `output_contract.result_json.required_fields/status_enum/evidence_item`，`result.build_result()` 把声明字段写到 `result.json` 顶层，状态统一为 `success|partial|unable`。
3. required_files 落盘：新增 `core/paperkit/deliver.py`，按 basename 分派处理器，覆盖 structure/body/refs/tables/bilingual/terms/entities/relations/graph/revised/changes/manuscript/methods/materials/latex/fix_report/compliance 等文件。
4. 状态门：`_validate_staged` 检查字段非空、状态枚举、evidence 的 anchor/quote、required_files 递归存在且非空；`success` 额外要求 change_log 非空。`run.py` 对 OCR 失败页和 PDF 低块数降级，文本输入不再误触块数门。

## 二、内容质量修复

- paper-parse：修表格断词（Concentration / Interfacial capacitance）、拆行内标题、参考文献按编号合并（9→6）、表格单元格造成的假章节。
- paper-nanopub：断言按分句抽取并保留逐字证据；R14-C01 由 1 条提升到 8 条，状态 success。
- paper-kg：新增五类实体抽取（Material/Method/Metric/Value/Claim），关系按 `uses/outperforms/supports/depends_on/contradicts` 输出；R15-C01 实体 35 个，R15-C02 对齐 9 簇并拆分 ASR 两义，R15-C05 保留 N01–N05/E01–E02 并续编 N06–N08/E03–E07，记录 42/96 冲突。
- paper-polish：规则化改写覆盖主谓一致、介词、分词悬垂、术语统一、去 overclaim、去口语化；W02-C01/C02/C03/C05 的 revised.md 已实际修改。
- paper-refs：按句主题匹配插入 `[n]`，W04-C01 的 8 篇文献全部挂载，输出 manuscript_cited.md 与 citation_placement.csv。
- paper-methods：从 experiment_log 生成 S1–S6（称量、装料球磨、过筛、压片、烧结冷却、EIS），物料设备表保留来源行。
- paper-intro：五个子任务分别生成 background、related work 分组、gap、contributions、引用覆盖表；引用只使用 W1–W8。
- paper-latex：复制 input/project 后最小修复（cite/natbib 冲突、cleveref 顺序、缺 amsmath、重复 label、未定义 eqref、宽表 resizebox、TODO 替换、bib 补条目、无依据引用降级），生成 compile.log 与 compliance.md。

## 三、本地评测结果

- 50/50 用例 `rc=0`。
- required_files 递归核对：170/170 存在且非空。
- 自检：50/50 通过。
- 状态分布：success 23、partial 26、unable 1。
- 唯一 unable：R01-C04，扫描 PDF 无 tesseract，OCR 无法产出文本。

## 四、仍为 partial 的原因

- 翻译、笔记、部分 refs、latex、W09-C02–C05 等用例的输入本身缺少可完整抽取的结构，交付文件已写出，但内容缺口在 `uncertainty.missing` 中列明。
- latex 5 例本地无 TeX 引擎，compile.log 记录为静态检查而非真实编译；未伪造编译成功。
- R01-C04 未伪造 OCR 结果。

## 五、复跑

```powershell
cd D:\github\2026-11-23-19-19-35
python tools\build_skills.py
python "C:\Users\王亮\Doubao\chats\2026-11-24\new-chat\_test_env\run_local_eval.py"
```

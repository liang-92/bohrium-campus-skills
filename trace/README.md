# trace/ 是什么

不是截图，也不是事后整理的对话。这是**平台会话日志直接转出来的执行轨迹**，
由 `tools/make_trace.py` 转换，只做两件事：按记录类型映射 `step_type`，以及脱敏。

| 文件 | 内容 | 规模 |
|---|---|---|
| `round2-steps.jsonl` | 第二轮（复核 + 修缺陷 + 建用例）的完整轨迹 | 815 步 |
| `steps.jsonl` | 第一轮（搭骨架）的轨迹，未随仓库分发（1.6 MB） | 1671 步 |

每行一条记录，字段含义：

| 字段 | 来源 |
|---|---|
| `step_type` | `thought` / `tool_call` / `tool_result` / `observation` |
| `tool_name`、`tool_args` | 平台记录的调用名与入参，未改写 |
| `tool_call_id` | 平台的 `callId`，因此 `tool_call` 与 `tool_result` 是真配对 |
| `timestamp` | 记录自带的毫秒时间戳，转 ISO-8601 |
| `step_order` | 原始顺序 |

`round2-steps.jsonl` 的实测统计：

```
step_type: tool_call 399, tool_result 398, thought 10, observation 8
配对工具调用: 398（仅 1 条未配对，是会话末尾被截断的最后一次调用）
不同时间戳: 815
时间跨度: 2026-11-23T13:16:43Z – 16:02:27Z（约 2 小时 46 分）
```

## 脱敏做了什么

1. `PLAYGROUND_TOKEN`、`ghp_*`、`github_pat_*`、`asp_*`、`sk-*` 形态的密钥 → `<REDACTED_TOKEN>`；
2. `password=` / `secret:` / `api_key=` 形态 → `<REDACTED>`；
3. 本地绝对路径里的用户名 → `<user>` / `<home>`（共 411 处）；
4. 会话里的系统提示块（`<system-reminder>` 等）整段跳过。

**没有**做的事：没有删掉失败的步骤，没有改写报错信息，没有补不存在的调用。
轨迹里能看到命令写错、`AttributeError`、用例失败这些真实记录——那正是它可信的原因。

## 自己重导

```bash
python tools/make_trace.py --session <session.jsonl> --out trace/steps.jsonl
```

会话文件在平台的会话目录里，`--format` 还支持 `conversation`（一问一答的简单形态）。

# 长任务拆成子任务：Agent 内部 todo 方案

## Context

现在 `codeAgent` 是一个黑盒节点：模型在一个 `create_agent` 循环里连跑几十个工具调用，前端只看到一个个工具名（`left/message.tsx` 把 `tool_calls` 的 name 排成一个 `<ul>`），用户看不出"现在做到第几步、还剩哪些"。长任务因此既不可观察，也容易在中途跑偏。

目标：让模型在动手前先拆出子任务清单，执行过程中逐条更新状态，前端实时看到一个进度列表。

**已确认的范围**：只做 Agent 内部 todo（单节点、单轮内可见），不做图级 plan→逐节点循环；不需要人工审批，模型拆完直接推进。

**关键发现（决定了实现路径）**：
- `langchain.agents.middleware.TodoListMiddleware` 自带 `write_todos` 工具 + `PlanningState.todos`，在 `.venv` 里现成可用，只需挂进 `code_agent.py:43` 的 `middleware=[...]`。
- 它写入的是 **子 agent 自己的 state**，不会自动流到外层图，也不会进 SSE（`custom` 通道由 `PROTOCOL_METHODS` 白名单放行）。
- `ToolRuntime` 暴露 `stream_writer`（`langgraph/runtime.py:116`），在工具里可以直接推 custom 事件 —— 这是把 todo 变化实时送出去最稳的入口。
- 前端 `@langchain/react` 有 `useExtension(stream, "todos")`，正是为 `custom:<name>` 的"最新值"设计的。
- 顺带修一个现有 bug：`plan_agent.py:22` 返回 `{"plan": []}`，而 `State` 没声明 `plan`，LangGraph 会抛 `InvalidUpdateError`。

---

## 后端（apps/api）

### 1. State 扩字段 — `src/app/agents/node/state.py`

在 `State` 里加：

```python
todos: NotRequired[list]   # 本轮子任务清单，LastValue 语义（写即覆盖）
```

同 `currentRoundMessages`：普通字段、不挂 reducer。注释说明这是子 agent 清单在外层图的镜像，只用于收尾/续跑时回读。

### 2. todo 中间件 — `src/app/agents/helper/middleware.py`

新增 `TodoTrackingMiddleware(TodoListMiddleware)`：

- 继承现成的 `TodoListMiddleware`（拿它的工具、系统提示、state_schema）。
- 覆写 `awrap_tool_call`（`langchain/agents/middleware/types.py:756`）：当 `request.tool_call["name"] == "write_todos"` 时，先 `await handler(request)`，再从返回的 `Command.update["todos"]` 读出最新清单，用 `request.runtime.stream_writer({...})` 推一条事件。其余工具原样透传。
- 事件形状定为 `{"name": "todos", "payload": {"todos": [...]}}` —— `normalize_event` 会把它包装成 `custom` + `{name, payload}`（`protocol.py:112-120`），或直接发成 `custom:todos`。两种形态前端用同一个 `useExtension` 读取。
- 放在 `helper/` 与 `TrackingSummarization` 并列，理由相同：可复用、与具体节点无关。

### 3. 挂到 codeAgent — `src/app/agents/node/code_agent.py`

- `middleware=[summarization, TodoTrackingMiddleware()]`。
- 节点返回值加上 `"todos": result.get("todos") or []`，把最终清单镜像进外层 `State`（供 `finish` 落库、供下一轮恢复）。

### 4. 收尾与历史

- `message_persistence.py` 不必改表：`write_todos` 的 tool_call 本身已经在 `currentRoundMessages` 里，`parts` 落库时天然带上 `args.todos`。**历史恢复不新增 schema** —— 前端从历史消息的 `tool_calls` 里取最后一次 `write_todos` 的 args 即可。
- `plan_agent.py`：把 `"plan": []` 删掉（占位节点不该写未声明字段），或在 `State` 补 `plan` 声明。推荐删掉，等真正做图级计划时再加。

---

## 前端（apps/web）

### 1. 取数 hook — 新建 `_components/hook/use-todos.ts`

- 当前值：`useExtension<{ todos: TodoItem[] }>(stream, "todos")`。
- 该 hook 同时打开 `custom:todos` 的订阅；后端 `matches_subscription`（`protocol.py:61`）对该通道放行。
- 历史值：从 `historyMessage` 里倒序找最后一条带 `write_todos` tool_call 的 AI 消息，取 `args.todos` 作为初值。
- 统一返回 `{ todos, done, total, current }`，`status` 取值 `pending | in_progress | completed`（与 `langchain/agents/middleware/todo.py` 的 `Todo` 一致）。

### 2. 展示组件 — 新建 `_components/left/todo-panel.tsx`

- 位置：`chat-pannel.tsx` 里放 `Composer` 上方、滚动区之外，常驻可见。
- 形态：默认收起的一行摘要 `已完成 3/8 · 正在做：接入 API 层`；点开是清单。
- 复用现有 shadcn 组件：`components/ui/spinner.tsx`（in_progress 图标）、`badge.tsx`、`separator.tsx`。收起/展开需要 `shadcn add collapsible`（当前未安装），或先用受控 `useState` + 条件渲染，避免引入依赖。
- `todos` 为空时不渲染（模型判断任务简单、不调 `write_todos` 时不应出现空面板）。

### 3. 消息气泡去噪 — `_components/left/message.tsx`

- `System` 组件里过滤掉 `write_todos` 这个名字，避免它混在 `read_file` / `bash` 之类的真实工具列表里。

---

## 验证

1. `make server` + `make dev-web`，在一个空项目里提一个多步需求（如"给首页加一个搜索框和对应的过滤逻辑"）。
2. 观察 SSE：`curl -N -X POST 'localhost:8000/agents/<id>/stream' -H 'accept: text/event-stream' -d '{}'`，应能看到 `custom:todos` 事件；`channels: ["custom:todos"]` 订阅也能拿到。
3. 前端：todo 面板出现、状态随工具调用推进；刷新页面后从历史恢复到同一条清单。
4. 旁路确认：只读小任务（"这个文件是干什么的"）不触发 `write_todos`，面板不出现。
5. `make lint`（后端 ruff/mypy、前端 eslint/prettier）+ `make typecheck`。
6. 回归：plan 模式跑一轮，确认 `planAgent` 不再因 `plan` 字段未声明而报 `InvalidUpdateError`。

## 不做的事

- 图级 plan → 逐子任务节点的循环编排（跨轮恢复、单步重跑）。需要时另开一轮，届时 `State.plan` 与 `codeStep` 节点一起设计。
- 人工审批（`HumanInTheLoopMiddleware` / `interrupt` + resume 命令入口）。当前 `agent_command` 只接受 `ChatCreateRequest`，没有 `Command(resume=...)` 分支，接它的成本远大于本次范围。

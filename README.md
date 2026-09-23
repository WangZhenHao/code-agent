# code-agent

对话式代码 Agent：一次会话 = 一个沙箱，Agent 在 k8s 沙箱内读写代码、执行命令，结果流式推给前端。

## 架构

```
Next.js (web)  ──SSE──▶  FastAPI + LangGraph (api)  ──▶  k8s Sandbox Pod (per session)
React SPA (admin) ──REST──┘
```

- **apps/web** — Next.js 用户端，对话 + 流式渲染
- **apps/admin** — React SPA（Vite）管理台
- **apps/api** — Python 后端，FastAPI + LangGraph，SSE 流式输出
- **packages/protocol** — 前后端共享的流式事件协议（JSON Schema → TS 类型）
- **deploy/** — 各组件与沙箱的部署配置

## 核心约定

1. **沙箱唯一入口**：所有代码执行都经 `apps/api/src/code_agent/sandbox/`，该目录之外不 import k8s 客户端，也绝不在 API Pod 内 `subprocess` 跑用户代码。
2. **本地开发用 docker provider**：`sandbox/docker.py` 一个容器即一个沙箱，避免每次改 prompt 都走 k8s。
3. **事件协议先行**：SSE 只传协议里定义的几种事件（token / tool_call / tool_result / file_diff / done / error），前端一个 reducer 消费。
4. **会话即 thread**：会话 ID = LangGraph `thread_id`，沙箱名与标签由它派生，沙箱生命周期绑定 thread 而非 HTTP 连接。
5. **API 无状态**：每次请求从 DB / checkpointer 取 thread_id 再向 sandbox 层要 handle，可随意扩缩容。

## 本地开发

```bash
make dev        # 起本地全栈
make lint       # 前后端 lint
make build      # 构建全部
```

依赖：Node ≥ 20 + pnpm，Python ≥ 3.11 + uv，Docker（本地沙箱）。

## 目录

```
apps/      web / admin / api
packages/  protocol（事件协议）
deploy/    web / admin / api / sandbox
docs/      设计文档
```

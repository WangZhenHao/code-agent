# code-agent-api

对话式代码 Agent 的后端：FastAPI 负责 HTTP/SSE，LangGraph 负责编排对话与工具调用。
一次会话对应一个沙箱，Agent 在沙箱内读写代码、执行命令。

- 运行环境：Python ≥ 3.12
- 包管理：uv
- 默认端口：**8000**

## 快速开始

```bash
# 安装依赖（uv 会自动按 .python-version 准备 3.12）
uv sync

# 启动（热重载跟随 CODE_AGENT_DEBUG，默认开启）
uv run code-agent-api
```

启动后：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/healthz | 健康检查，返回 `{"status":"ok","version":"..."}` |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |

也可以用模块方式启动（等价）：

```bash
uv run python -m code_agent_api.main
```

## 技术栈

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| fastapi[standard] | 0.141.1 | HTTP 框架，`[standard]` 已含 uvicorn / watchfiles |
| langchain | 1.4.2 | 工具与模型抽象 |
| langgraph | 1.2.12 | Agent 状态机编排 |
| pydantic-settings | 2.15.0 | 配置加载 |
| uvicorn | 0.53.0 | ASGI Server |

## 目录结构

```
src/code_agent_api/
├── __init__.py        # 版本号
├── main.py            # create_app() + /healthz + main() 启动入口
└── settings.py        # 配置（环境变量前缀 CODE_AGENT_）
```

规划中（尚未实现）：

```
src/code_agent_api/
├── api/routes/        # chat(SSE) / sessions / sandbox
├── graph/             # LangGraph：state / builder / nodes / checkpoint
├── tools/             # Agent 可调用的能力：fs / shell / git
├── sandbox/           # 沙箱抽象：base / docker / kubernetes
└── events/            # 流式事件模型（与 packages/protocol 同源）
```

## 配置

全部通过环境变量注入，前缀 `CODE_AGENT_`，也支持在 `apps/api/.env` 中写（已被 gitignore）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CODE_AGENT_APP_NAME` | `code-agent-api` | 应用名，出现在 OpenAPI 文档 |
| `CODE_AGENT_HOST` | `0.0.0.0` | 监听地址 |
| `CODE_AGENT_PORT` | `8000` | 监听端口 |
| `CODE_AGENT_DEBUG` | `true` | 同时控制 FastAPI debug 与 uvicorn 热重载 |
| `CODE_AGENT_SANDBOX_PROVIDER` | `docker` | 沙箱实现，本地 `docker`、集群 `kubernetes` |
| `CODE_AGENT_SANDBOX_NAMESPACE` | `code-agent-sandboxes` | 沙箱 Pod 所在 namespace |

例：临时换端口跑

```bash
CODE_AGENT_PORT=9000 uv run code-agent-api
```

## 核心约定

1. **沙箱是唯一的代码执行入口**。`tools/` 里的 shell/文件操作一律经 `sandbox/` 抽象层，绝不在 API 进程内用 `subprocess` 跑用户代码。
2. **`sandbox/` 之外不 import k8s 客户端**。集群实现只是抽象层的一个 provider，本地用 docker provider，避免改一行 prompt 就要走一遍镜像构建。
3. **API 层无状态**。会话 ID 即 LangGraph `thread_id`，沙箱名由它派生；请求从 checkpointer 取 thread_id 再向沙箱层要 handle，因此可以随意扩缩容和滚动更新。
4. **SSE 只传协议里定义的事件**（token / tool_call / tool_result / file_diff / done / error），协议定义在 `packages/protocol`，前后端共用。

## 与其他子项目的关系

| 目录 | 关系 |
| --- | --- |
| `apps/web` | Next.js 用户端，经 Route Handler 代理转发本服务的 SSE |
| `apps/admin` | React SPA 管理台，生产走 nginx 反代 `/api/` 到本服务 |
| `packages/protocol` | 流式事件协议的唯一来源，本服务的 `events/` 与之同源 |
| `deploy/api` | 本服务的 k8s 清单（Deployment / Service / RBAC） |

开发期 CORS 已放行 `http://localhost:3000`（web）与 `http://localhost:5174`（admin）。

## 常用命令

```bash
uv sync                    # 安装/同步依赖
uv add <pkg>               # 新增依赖
uv run code-agent-api      # 启动服务
uv run pytest              # 跑测试（尚未接入）
uv run ruff check .        # lint（尚未接入）
```

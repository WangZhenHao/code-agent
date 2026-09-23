# code-agent-api

对话式代码 Agent 的后端：FastAPI 负责 HTTP/SSE，LangGraph 负责编排对话与工具调用。
一次会话对应一个沙箱，Agent 在沙箱内读写代码、执行命令。

## 快速开始

```bash
# 安装依赖（uv 会自动按 .python-version 准备 3.12）
uv sync

docker-compose up -d

# 启动（热重载跟随 CODE_AGENT_DEBUG，默认开启）
uv run code-agent-api
```

启动后：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |

也可以用模块方式启动（等价）：

```bash
uv run python -m app.main
```

## 技术栈

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| fastapi[standard] | 0.141.1 | HTTP 框架，`[standard]` 已含 uvicorn / watchfiles |
| langchain | 1.4.2 | 工具与模型抽象 |
| langgraph | 1.2.12 | Agent 状态机编排 |
| sqlalchemy | 2.0.54 | ORM（async，驱动 asyncpg） |
| alembic | 1.20.0 | 数据库迁移 |
| pydantic-settings | 2.15.0 | 配置加载 |
| uvicorn | 0.53.0 | ASGI Server |

## 目录结构

```
apps/api/
├── alembic/           # 迁移脚本；env.py 从 app.settings 取连接串
├── alembic.ini        # sqlalchemy.url 留空，由 env.py 覆盖
└── src/app/
    ├── __init__.py        # 版本号
    ├── main.py            # create_app() + main() 启动入口
    ├── settings.py        # 配置（环境变量前缀 CODE_AGENT_）
    ├── api/               # 路由：chat / agent（router + schemas + service 三层）
    ├── agents/            # LangGraph 编排：graphs / memory / tools
    ├── db/
    │   ├── base.py        # Base（含约束命名约定）+ TimestampMixin
    │   ├── session.py     # async engine / SessionLocal / get_session 依赖
    │   └── models/        # 表模型；__init__.py 必须 import 全部模型供 autogenerate 发现
    └── models/            # LLM 客户端（注意：与 db/models 不是一回事）
```

规划中（尚未实现）：

```
src/app/
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
| `CODE_AGENT_CORS_ORIGINS` | `http://localhost:3000,http://localhost:5174` | 允许跨域的前端来源，逗号分隔；生产走同源反代可留空 |
| `CODE_AGENT_DATABASE_URL` | — | Postgres 连接串（**必填**），驱动段必须是 `postgresql+asyncpg` |
| `CODE_AGENT_REDIS_URL` | — | Redis 连接串（**必填**） |

`database_url` / `redis_url` 没有默认值：字段是必填的，漏配会在进程启动时直接报错，
而不是跑到一半才失败。

例：临时换端口跑

```bash
CODE_AGENT_PORT=9000 uv run code-agent-api
```

## 数据库

本地 Postgres 由 `docker-compose.yml` 提供，宿主机端口 **5433**（刻意避开默认的 5432，
防止和机器上已有的 Postgres 撞车），数据落在 `postgres-data` 卷里。

```bash
docker-compose up -d                                       # 起 Postgres + Redis
cd apps/api && uv run alembic upgrade head                 # 建表/升级到最新
uv run alembic revision --autogenerate -m "add xxx"        # 改完模型后生成迁移
uv run alembic check                                       # 检查模型与库是否已同步
```

约定：

- **建表只走迁移，不用 `create_all`**。迁移文件在 `alembic/versions/` 下，提交进仓库。
- **新增表模型后必须在 `src/app/db/models/__init__.py` 里 import 一次**。autogenerate 只看得见
  已经注册进 `Base.metadata` 的类，漏 import 的表现是它以为你要删表。
- **约束名走 `db/base.py` 里的命名约定**（`pk_/uq_/ix_/fk_/ck_`）。不约定的话 Postgres 自动起的名字
  在不同环境可能不一致，迁移会反复产生无意义的重命名 diff。
- **可空唯一列用 partial unique index**（`uq_users_email` 等带 `WHERE ... IS NOT NULL`）。
  语义上表达「只对非空值去重」，迁移文件里意图一目了然。
- 连接串只在 `.env` 里配置一处，`alembic.ini` 的 `sqlalchemy.url` 留空，由 `alembic/env.py`
  从 `app.settings` 读取——本地 / CI / 生产共用同一份迁移代码。

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

**数据库 schema 由本服务独占**：前端项目（web / admin）不直连 Postgres，也不要另建一套
ORM/迁移指向同一个库——两边各写各的迁移，字段所有权立刻分叉，迟早互相打架。前端要数据
就走本服务的 HTTP 接口。

开发期 CORS 已放行 `http://localhost:3000`（web）与 `http://localhost:5174`（admin）。

## 常用命令

```bash
uv sync                    # 安装/同步依赖
uv add <pkg>               # 新增依赖
uv run code-agent-api      # 启动服务
uv run alembic upgrade head    # 应用迁移
uv run alembic revision --autogenerate -m "msg"   # 生成迁移（需先起 Postgres）
uv run pytest              # 跑测试（尚未接入）
uv run ruff check .        # lint（尚未接入）
```

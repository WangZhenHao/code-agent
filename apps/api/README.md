# code-agent-api

对话式代码 Agent 的后端：FastAPI 负责 HTTP/SSE，LangGraph 负责编排对话与工具调用。
一次会话对应一个沙箱，Agent 在沙箱内读写代码、执行命令。

## 快速开始

```bash
# 安装依赖（uv 会自动按 .python-version 准备 3.12）
uv sync

# 起 Postgres + Redis
docker-compose up -d

# 建表/升级到最新
uv run alembic upgrade head                 

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

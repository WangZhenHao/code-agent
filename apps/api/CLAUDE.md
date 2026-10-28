# apps/api

@README.md

上面引入的 README 是主要说明书（技术栈、目录、alembic 约定、启动方式都在里面）。以下是 README 之外容易踩的点。

## 目录

- `api/` 下按领域分：`chat/`、`user/`、`agent/`、`sandbox/`、`session/`，每个模块是 `router.py + schemas.py + service.py`
- `agents/graphs.py`（LangGraph 图）、`agents/node/`、`agents/tools/`、`agents/memory/`、`agents/threading/`、`agents/helper/`、`agents/message_persistence.py`
- 另有顶层 `redis.py`、`security.py`
- 只起后端在仓库根用 `make server`，不是 `make dev-api`。

## 命名陷阱

`src/app/db/models/` 是数据库表模型；`src/app/models/` 是 **LLM 客户端**。两处不同物，改之前看清楚路径。

## 必须遵守

- 所有 Python 命令走 `uv run`（`uv run alembic ...`、`uv run python -m unittest ...`）。
- 建表只走 alembic 迁移，不用 `create_all`。改完模型 → `make db-revision m="..."` → `make db-check`。
- 新增表模型必须在 `src/app/db/models/__init__.py` import 一次，否则 autogenerate 会以为你要删表。
- 测试是 `python -m unittest discover -s tests`，仓库没装 pytest。

## 对外契约

`/openapi.json` 会被 `apps/web` 的 orval 消费生成前端类型。改接口路径或字段后要提醒前端跑 `make gen-api`。SSE 接口（`/agents/talking/*`、`/agents/retalk/*`）不生成，前端手写。

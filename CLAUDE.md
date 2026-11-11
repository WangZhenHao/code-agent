# code-agent

对话式代码 Agent：一次会话 = 一个 k8s 沙箱，Agent 在沙箱内读写代码、执行命令，结果通过 SSE 流式推给前端。

```
apps/web   (Next.js :3000)   ──SSE──▶
                                    apps/api (FastAPI + LangGraph :8000) ──▶ k8s Sandbox Pod (per session)
apps/admin (Vite+React :5174) ──REST──▶
```

## 三个 app

| 目录 | 技术栈 | 职责 | 详细约定 |
| --- | --- | --- | --- |
| `apps/api` | Python 3.12 / FastAPI / LangGraph / SQLAlchemy(async) | HTTP + SSE 接口、Agent 编排、沙箱调度、数据库 | `apps/api/CLAUDE.md` + `apps/api/README.md` |
| `apps/web` | Next.js (App Router) / Tailwind / shadcn / zustand | 用户端对话界面，流式渲染 | `apps/web/CLAUDE.md` |
| `apps/admin` | Vite / React 19 / Ant Design / Tailwind | 管理台 | `apps/admin/CLAUDE.md` |

其他目录：`deploy/`（沙箱 CRD、router、镜像、Ingress 的 k8s 清单与安装脚本）、`docs/`、`templete/`（沙箱内项目模板）。

## 本地依赖服务

- Postgres **5433**（业务表 + LangGraph checkpointer）、Redis **6380** — 由 `apps/api/docker-compose.yml` 提供，刻意避开默认端口
- k8s（OrbStack）：沙箱控制器 + router，装法见 `README.md`
- `apps/api/.env` 至少需要 `CODE_AGENT_API_KEY`、`CODE_AGENT_API_URL`

## 命令

```bash
make install        # 装全部依赖（web + admin + api）
make dev            # 只起 web + admin（并行）
make dev-web        # Next.js :3000
make dev-admin      # React SPA :5174
make server         # FastAPI :8000 —— README 里写的 make dev-api 不存在，target 叫 server
make gen-api        # 后端 OpenAPI → 前端类型/hooks（需先起 api）
make db-up / db-migrate / db-revision m="msg" / db-check
make lint           # 前端 eslint + prettier 检查，后端 ruff + ruff format --check + mypy
make lint-fix       # lint 自动修复
make typecheck      # 前端 tsc
make fmt / fmt-check  # 格式化全部 / 只检查
make test / build
```

`make test` 跑的是 `python -m unittest`，不是 pytest。

两个前端统一 **ESLint 9（flat config）+ Prettier**，配置各自留在 app 目录内（`eslint.config.*`、`.prettierrc`）——仓库不是 workspace，依赖按 app 各自安装。
后端是 **ruff**（格式化 + lint）+ **mypy**（类型检查），配置在 `apps/api/pyproject.toml` 的 `[tool.ruff]` / `[tool.mypy]`。

## 跨 app 约定（最容易漏）

- **改了后端接口（路径/字段）必须跑 `make gen-api`**，重新生成 `apps/web/src/api/generated/`；不要手改这个目录。
- orval 生成不了 SSE 接口（`/agents/talking/*`、`/agents/retalk/*` 在 `apps/web/orval.config.ts` 里被主动剔除），这两个是手写的 fetch。
- Python 命令一律 `uv run`，不要用系统 python。

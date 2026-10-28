@AGENTS.md

> `AGENTS.md` 由 `next dev` 自动生成和重写，**不要往里加自定义内容**（会被覆盖）。本项目的约定写在本文件里。

## 是什么

用户端对话界面：Next.js App Router，对话 + SSE 流式渲染 Agent 输出。通过后端 `apps/api`（:8000）通信。

## 目录

```
src/
├── app/                    # App Router
│   ├── (home)/ (console)/ (detail)/   # 路由组
│   ├── layout.tsx  globals.css
├── api/
│   ├── generated/          # orval 生成，勿手改
│   └── http.ts             # orval mutator（axios 实例）
├── components/
│   ├── ui/                 # shadcn 组件（components.json 配置）
│   ├── custom/             # 业务组件
│   └── providers/
├── hooks/
├── lib/
│   ├── agent-stream/       # SSE 流消费
│   ├── auth.ts  chat-options.ts  utils.ts
├── store/                  # zustand：agent-chat.ts / user.ts
└── proxy.ts
```

## 约定

- **API 类型和 hooks 一律由 orval 生成**（`orval.config.ts`，tags-split → `src/api/generated/`，react-query + axios）。不要手写接口类型；后端改了就跑 `make gen-api`（需先起 api，读 `http://localhost:8000/openapi.json`）。
- SSE 接口生成不出来，被 `SSE_PATHS` 主动剔除，走 `src/lib/agent-stream/` 手写 fetch。
- 样式：Tailwind + shadcn。新增 UI 组件用 `shadcn` skill、放 `components/ui/`；业务组件放 `components/custom/`。
- 状态：zustand（`src/store/`），注意流式输出时的增量更新。
- lint 是 eslint（`make lint` 里跑 `pnpm lint`）；包管理用 pnpm。

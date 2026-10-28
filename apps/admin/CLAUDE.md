# apps/admin

管理台（React SPA），与面向用户的 `apps/web` 是独立的两个前端，共同对接 `apps/api`。

## 技术栈

Vite 8 + React 19 + TypeScript，UI 用 Ant Design（antd 6），路由 react-router-dom 7，样式 Tailwind 4（`@tailwindcss/vite`）。入口 `src/main.tsx` → `App.tsx`。

## 目录

```
src/
├── main.tsx  App.tsx  index.css
├── layout/          # AdminLayout / HeaderBar / SideNav
└── api/types.ts     # 接口类型（手写，不是生成代码）
```

## 约定

- **lint 用 oxlint，不是 eslint**（`pnpm lint` → `oxlint`，配置 `.oxlintrc.json`）。
- UI 组件优先用 antd，不要再引入第二套组件库；不要从 `apps/web` 的 shadcn 组件里复制。
- `src/api/types.ts` 是手写类型，和 `apps/web` 的 orval 生成代码没有共享。
- 与 `apps/web` 的不同点：一个走 REST、一个走 SSE；admin 不需要流式渲染。
- 开发端口 5174（`make dev-admin`）。

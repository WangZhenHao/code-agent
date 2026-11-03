# apps/admin

管理台（React SPA），Vite + React + TypeScript，UI 用 Ant Design。

## 常用命令

```bash
pnpm dev          # 本地开发（:5174）
pnpm build        # tsc -b && vite build
pnpm lint         # eslint --max-warnings 0
pnpm lint:fix     # eslint --fix
pnpm format       # prettier --write .
pnpm format:check # prettier --check .
pnpm typecheck    # tsc -b --noEmit
```

## Lint 与格式化

ESLint 9 flat config（`eslint.config.js`）：`@eslint/js` + `typescript-eslint` 的
`recommendedTypeChecked` + `eslint-plugin-react-hooks` + `eslint-plugin-react-refresh`，
与 `apps/web` 同一套工具链。格式化是 Prettier（`.prettierrc`），与 ESLint 解耦——
格式问题由 `pnpm format:check` 负责，不进 lint 报错。

类型感知规则依赖 `tsconfig.app.json`，所以 `pnpm typecheck` 必须带 `-b`：根
`tsconfig.json` 只有 project references，裸跑 `tsc --noEmit` 什么都不检查。

项目约定见 [CLAUDE.md](./CLAUDE.md)。

import js from "@eslint/js"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"
import tseslint from "typescript-eslint"
import prettier from "eslint-config-prettier/flat"

export default tseslint.config(
  { ignores: ["dist", "dist-ssr", "node_modules"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      parserOptions: {
        // tsconfig.json 是 project references 的入口，projectService 会自动
        // 匹配到 tsconfig.app.json / tsconfig.node.json
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  prettier
)

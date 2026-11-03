import { defineConfig, globalIgnores } from "eslint/config"
import nextVitals from "eslint-config-next/core-web-vitals"
import nextTs from "eslint-config-next/typescript"
import tsEslint from "typescript-eslint"
import prettier from "eslint-config-prettier/flat"

// eslint-config-next 已经注册了 @typescript-eslint 插件（第 0 项）。
// 这里只取规则集，剥掉 plugins 字段，避免 flat config 里重复定义插件。
const typeChecked = tsEslint.configs.recommendedTypeChecked.map((config) => {
  const rulesOnly = { ...config }
  delete rulesOnly.plugins
  return rulesOnly
})

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // 类型感知规则只作用于 TS 源码；.mjs 配置文件不在 tsconfig 的 include 里
    files: ["**/*.ts", "**/*.tsx"],
    extends: typeChecked,
    languageOptions: {
      // web 解析到 TypeScript 5.0.2，低于 projectService 要求的 5.4
      parserOptions: {
        project: ["./tsconfig.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  prettier,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Orval 生成产物，不参与 lint
    "src/api/generated/**",
  ]),
])

export default eslintConfig

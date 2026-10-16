import { defineConfig } from "orval"

export default defineConfig({
  user: {
    input: "./node_modules/.cache/user-openapi.json",
    output: {
      client: "axios-functions",
      mode: "single",
      target: "./src/generated/user-api.ts",
      schemas: { path: "./src/generated/user-models.ts", mode: "single" },
    },
  },
})

import { defineConfig } from "orval";
import type { OpenApiDocument } from "orval";

/** SSE 流式接口：生成出来是普通 promise，没法消费流，单独手写 fetch */
const SSE_PATHS = [
  "/agents/talking/{session_id}",
  "/agents/retalk/{session_id}",
] as const;

const dropSsePaths = (spec: OpenApiDocument): OpenApiDocument => {
  const paths = { ...spec.paths };
  for (const path of SSE_PATHS) delete paths[path];
  return { ...spec, paths };
};

export default defineConfig({
  api: {
    input: {
      target: "http://localhost:8000/openapi.json",
      // filters 在 v8 只支持按 tag/schema 过滤，粒度到不了单条接口，这里用 transformer 精确剔除
      override: { transformer: dropSsePaths },
    },
    output: {
      mode: "tags-split",
      target: "src/api/generated/endpoints.ts",
      schemas: "src/api/generated/model",
      client: "react-query",
      httpClient: "axios",
      clean: true,
      mock: false,
      override: {
        mutator: { path: "./src/api/http.ts", name: "customInstance" },
        query: {
          // 不设全局 useQuery：默认 GET → useQuery，非 GET → useMutation
          useInfinite: true,
          useInfiniteQueryParam: "cursor",
        },
      },
    },
  },
});

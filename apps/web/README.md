# web

Next.js App Router 前端。

## 技术栈

- Next.js 16 / React 19 / TypeScript
- Tailwind CSS v4 + shadcn/ui
- TanStack Query v5 + axios
- Orval：从后端 OpenAPI 自动生成类型与 hooks

## 接口层

### 目录

```
src/api/
├── http.ts              # 手写：axios 实例 + Orval mutator
└── generated/           # 自动生成，不要手改
    ├── agent/agent.ts
    ├── chat/chat.ts
    ├── user/user.ts
    └── model/           # 请求/响应类型
```

### 环境变量

复制 `.env.example` 为 `.env.local`：

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

不配也有默认值 `http://localhost:8000`。请求头会自动带上 `Authorization: Bearer <token>`，token 从 `localStorage.getItem("token")` 读取。

### 重新生成

后端接口变了先起 `make dev-api`，再：

```bash
pnpm gen:api        # 或在仓库根 make gen-api
```

### 生成规则

- HTTP GET → `useXxx`（`useQuery`），非 GET → `useXxx`（`useMutation`）
- 请求体类型的 mutation 变量是 `{ data: Body }`；只有路径参数的 mutation 变量是 `{ id }` 这类
- SSE 流式接口（`/agents/talking`、`/agents/retalk`）被 [orval.config.ts](orval.config.ts) 的 transformer 排除，需要手写 `fetch` + `ReadableStream`
- 全量类型在 `src/api/generated/model/index.ts`，也可以直接 `import type { ChatDetailResponse } from "@/api/generated/model"`

`QueryProvider`（`src/components/providers/query-provider.tsx`）已在 `app/layout.tsx` 挂好，页面里不需要再包一层。

---

## 使用示例

### 1. GET：查询详情

```tsx
"use client";

import { useDetailChatDetailIdGet } from "@/api/generated/chat/chat";

export function ChatDetail({ id }: { id: string }) {
  const { data, isLoading, error } = useDetailChatDetailIdGet(id);

  if (isLoading) return <p>加载中…</p>;
  if (error) return <p>加载失败：{error.message}</p>;

  return (
    <div>
      <h2>{data?.title}</h2>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
```

hook 会自动带上 `queryKey`（`["/chat/detail/xxx"]`），并发去重和缓存都由 TanStack Query 处理。

### 2. POST：提交表单（mutation）

```tsx
"use client";

import { useState } from "react";
import { useUserSendCodeUserSendCodePost } from "@/api/generated/user/user";

export function SendCodeForm() {
  const [phone, setPhone] = useState("");
  // mutation 变量是 { data: 请求体 }
  const { mutate, isPending, data, error } = useUserSendCodeUserSendCodePost();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutate({ data: { phone } });
      }}
    >
      <input value={phone} onChange={(e) => setPhone(e.target.value)} />
      <button disabled={isPending}>{isPending ? "发送中…" : "发送验证码"}</button>
      {data && <p>已发送，{data.expires_in} 秒内有效</p>}
      {error && <p>{error.message}</p>}
    </form>
  );
}
```

### 3. 登录 + 存 token + 刷新用户信息

```tsx
"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  useUserLoginUserLoginPost,
  useUserMeUserMeGet,
  getUserMeUserMeGetQueryKey,
} from "@/api/generated/user/user";

export function LoginAndProfile() {
  const queryClient = useQueryClient();
  const { data: me } = useUserMeUserMeGet();
  const login = useUserLoginUserLoginPost({
    mutation: {
      onSuccess: (res) => {
        // http.ts 的拦截器会读这个 key
        localStorage.setItem("token", res.access_token);
        queryClient.invalidateQueries({ queryKey: getUserMeUserMeGetQueryKey() });
      },
    },
  });

  return (
    <div>
      <p>{me ? `已登录：${me.phone}` : "未登录"}</p>
      <button
        disabled={login.isPending}
        onClick={() => login.mutate({ data: { phone: "13800138000", code: "123456" } })}
      >
        登录
      </button>
    </div>
  );
}
```

### 4. 不带 hook：在事件回调里直接调

命令式场景（比如点击后跳转）用底层函数即可，签名和 hook 一致：

```ts
import { sessionDeleteSessionDeleteIdPost } from "@/api/generated/session/session";

await sessionDeleteSessionDeleteIdPost(id);
```

### 5. 错误处理

`http.ts` 会把非 2xx 统一转成 `ApiError`：

```ts
import { ApiError } from "@/api/http";

if (error instanceof ApiError && error.status === 401) {
  // 跳登录
}
```

`error.body` 是后端返回的原始 JSON，`error.message` 优先取 FastAPI 的 `detail` 字段。

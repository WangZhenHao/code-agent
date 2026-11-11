/**
 * @langchain/react 接入本项目 Agent Streaming Protocol 的适配层。
 *
 * SDK 期望的线上格式是 LangGraph 协议：
 *   - 命令：`{ id, method: "run.start", params: { input: { messages }, … } }`
 *   - 路径：`/threads/:id/commands`、`/threads/:id/stream/events`
 *
 * 本项目的后端（apps/api/src/app/api/agent/router.py）是精简版：
 *   - 命令体直接就是 `ChatCreateRequest`：`{ model, mode, parts }`
 *   - 路径是 `/agents/:id/commands`、`/agents/:id/stream`
 *
 * 事件流的线格式两边是一致的（后端 protocol.py 就是按 SDK 的
 * MessageAssembler 对齐的），所以只需要改写请求、重定向路径，
 * SSE 响应交回 SDK 自己解析。
 */

import { Client as LangGraphClient } from "@langchain/langgraph-sdk"
import { HttpAgentServerAdapter } from "@langchain/react"

import { useUserStore } from "@/store/user"

export const AGENT_API_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

/**
 * 给 `StreamProvider` 用的 LangGraph Client。
 *
 * SDK 的 hydrate 流程在拿到真实 state（threadExists=true）后还会调
 * `client.threads.getHistory()` 做 subagent / subgraph 的命名空间发现——它
 * **不走 transport 的 paths 配置**，而是 SDK 内部拼 `/threads/{id}/history`，
 * 我们的后端没有这个路由，于是一次 hydrate 一个被静默吞掉的 404。
 *
 * 本项目的图没有 subagent / 子图，发现结果一律用不上，所以直接 stub 成空页：
 * 零网络请求、零 404。将来接入 subagent 卡片时要换成真实实现。
 */
export function createAgentClient() {
  const client = new LangGraphClient({ apiUrl: AGENT_API_URL })
  client.threads.getHistory = () => Promise.resolve([])
  return client
}

/** 后端取会话归属用的 session_id，即路由里的项目 id。 */
export function agentPaths(sessionId: string) {
  return {
    commands: `/agents/${sessionId}/commands`,
    stream: `/agents/${sessionId}/stream`,
    // hydrate 探测：线程是否存在、本轮是否仍在跑。SDK 据此决定挂载时要不要
    // 立即开 SSE——idle 线程推迟到首次 submit，不再对已结束的轮次白重放。
    state: `/agents/${sessionId}/state`,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

/**
 * 命令信封 → 后端请求体。
 *
 * 后端 `/agents/{id}/commands` 收的就是 `ChatCreateRequest`（`{ model, mode, parts }`），
 * 而 Composer 提交的 input 本身已经是这个形状（`stream.submit(prompt)`）。所以
 * 只需要把 `params.input` 原样取出来——不需要逐字段映射。
 */
function commandBody(command: Record<string, unknown>): string {
  const params = isRecord(command.params) ? command.params : {}
  const input = isRecord(params.input) ? params.input : {}
  return JSON.stringify(input)
}

/**
 * 构造绑定到某个会话的 adapter。
 *
 * 每个会话一个实例：路径是固定的，换了会话就该重建（配合 StreamProvider 的
 * `key` 一起换，避免旧流的状态串到新会话）。
 */
export function createAgentTransport(sessionId: string) {
  const transport = new HttpAgentServerAdapter({
    apiUrl: AGENT_API_URL,
    threadId: sessionId,
    paths: agentPaths(sessionId),
    onRequest: (_url, init) => {
      // 鉴权走 http.ts 那一套：令牌存在 zustand persist 里，这里读出来补头。
      const token = useUserStore.getState().token
      const headers = new Headers(init.headers)
      if (token) headers.set("Authorization", `Bearer ${token}`)

      // 命令请求体改写成 ChatCreateRequest；stream/state 的 POST body
      // （SubscribeParams）本来就和后端一致，原样放行。
      let body = init.body
      if (typeof body === "string") {
        try {
          const parsed = JSON.parse(body) as unknown
          if (isRecord(parsed) && "method" in parsed) {
            body = commandBody(parsed)
          }
        } catch {
          // 不是 JSON 就原样发出去，让后端返回明确的 422。
        }
      }

      return { ...init, headers, body }
    },
  })

  // hydrate 走 `GET /agents/{id}/state`（由 HttpAgentServerAdapter 内置的
  // getState 发出，因为它绑定的是 SSE transport）。后端返回 `values`（空）+
  // `next`（空数组 = 本轮已结束）。SDK 据 `next` 判断 threadActive——idle 时
  // 推迟打开 root pump，刷新进页面不再白重放上一轮；`values` 故意不带 messages，
  // 完整历史仍由 `/chat/message/{id}` 提供（checkpoint 里的是压缩后的工作上下文）。
  // 404 → SDK 收到 null，当作「线程不存在」并把 pump 停靠到首次 submit。
  // 不要再覆盖 transport.getState：覆盖成 null 会让每个线程都按「活跃」处理。

  return transport
}

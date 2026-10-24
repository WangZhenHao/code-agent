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

import { HttpAgentServerAdapter } from "@langchain/react";

import { useUserStore } from "@/store/user";

export const AGENT_API_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** 后端取会话归属用的 session_id，即路由里的项目 id。 */
export function agentPaths(sessionId: string) {
  return {
    commands: `/agents/${sessionId}/commands`,
    stream: `/agents/${sessionId}/stream`
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * 命令信封 → 后端请求体。
 *
 * 后端 `/agents/{id}/commands` 收的就是 `ChatCreateRequest`（`{ model, mode, parts }`），
 * 而 Composer 提交的 input 本身已经是这个形状（`stream.submit(prompt)`）。所以
 * 只需要把 `params.input` 原样取出来——不需要逐字段映射。
 */
function commandBody(command: Record<string, unknown>): string {
  const params = isRecord(command.params) ? command.params : {};
  const input = isRecord(params.input) ? params.input : {};
  return JSON.stringify(input);
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
      const token = useUserStore.getState().token;
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);

      // 命令请求体改写成 ChatCreateRequest；stream/state 的 POST body
      // （SubscribeParams）本来就和后端一致，原样放行。
      let body = init.body;
      if (typeof body === "string") {
        try {
          const parsed = JSON.parse(body) as unknown;
          if (isRecord(parsed) && "method" in parsed) {
            body = commandBody(parsed);
          }
        } catch {
          // 不是 JSON 就原样发出去，让后端返回明确的 422。
        }
      }

      return { ...init, headers, body };
    },
  });

  // 后端没有 state 接口（hydrate 只会在挂载时调一次 transport.getState）。
  // SDK 在 getState 存在时一定发起 `GET /threads/{id}/state`；删掉它又会回退到
  // customize 分支里不存在的 `client.threads.getState()` 直接抛错。所以保留方法、
  // 返回 null：SDK 把 null 当作"没有历史"（不会当成 404 记进 missingThreadIds），
  // 历史交给 /stream 的回放（后端默认 since 缺省 ⇒ 从 seq 0 全量回放）。
  transport.getState = async () => null;

  return transport;
}

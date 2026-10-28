/**
 * 会话级 WebSocket 客户端（JSON-RPC 2.0）。
 *
 * 一个 session 只许有一条连接（后端每个连接都会订阅一遍 devbox 并各跑一份心跳，
 * 多开则同一条推送会被重复收到），所以这里是一个手写的单连接封装，
 * 而不是每次调用都 `new WebSocket()`。
 *
 * 协议见 apps/api/src/app/api/ws/ws.md，前端只需要两条约定：
 *   - 有 `id` 的是应答（这里全部丢弃，业务数据都走推送）
 *   - 没有 `id` 的是推送，按 `method` 分发给订阅者；`ping` 是心跳，静默忽略
 */

import { AGENT_API_URL } from "@/lib/agent-stream/agent-stream";
import { useUserStore } from "@/store/user";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

/** 握手被拒的关闭码：重连也没用 */
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_FORBIDDEN_ORIGIN = 4403;
const CLOSE_DEVBOX_NOT_FOUND = 4404;

type Handler = (params: Record<string, unknown>) => void;

export interface WsClient {
  /** 发起连接；重复调用无副作用 */
  connect(): void;
  /** 主动断开且不再重连（组件卸载时用） */
  close(): void;
  /** 发一条 JSON-RPC 请求（不等应答） */
  sendWs(method: string, params: Record<string, unknown>): void;
  /** 订阅某条推送；返回退订函数 */
  subscribe(method: string, handler: Handler): () => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** http(s)://host → ws(s)://host/ws/devbox/{id}?token=… */
function buildUrl(devboxId: string, token: string | null): string {
  const wsBase = AGENT_API_URL.replace(/\/$/, "").replace(/^http/, "ws");
  const base = `${wsBase}/ws/devbox/${encodeURIComponent(devboxId)}`;
  // 浏览器 WebSocket 构造函数设不了请求头，令牌只能走 query。
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

export function createWsClient({ devboxId }: { devboxId: string }): WsClient {
  let ws: WebSocket | null = null;
  let closedByUs = false;
  let reconnectAttempt = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let nextId = 1;

  // CONNECTING 时 send() 会抛 InvalidStateError，先排队、连上后一起发（ws.md 做法 A）。
  const queue: string[] = [];

  const handlers = new Map<string, Set<Handler>>();

  function rawSend(text: string) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(text);
    } else {
      queue.push(text);
    }
  }

  function flushQueue() {
    if (!ws) return;
    while (queue.length && ws.readyState === WebSocket.OPEN) {
      ws.send(queue.shift()!);
    }
  }

  function dispatch(method: string, params: Record<string, unknown>) {
    const set = handlers.get(method);
    if (!set) return; // 不认识的 method 静默忽略——后端随时可能加新推送
    for (const handler of set) {
      try {
        handler(params);
      } catch (error) {
        // 单个订阅者报错不能拖垮连接和其余订阅者
        console.error(`ws handler error: ${method}`, error);
      }
    }
  }

  function scheduleReconnect() {
    if (closedByUs || reconnectTimer) return;
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** reconnectAttempt,
      RECONNECT_MAX_MS,
    );
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, delay);
  }

  function open() {
    if (closedByUs) return;
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    // 每次建连时现读令牌：persist 回填晚于首屏挂载，捕获进闭包会拿到 null，
    // 那样握手会被 4401 拒掉。
    const token = useUserStore.getState().token;
    if (!token) {
      console.warn("ws: 没有令牌，跳过连接");
      return;
    }

    ws = new WebSocket(buildUrl(devboxId, token));

    ws.onopen = () => {
      reconnectAttempt = 0;
      flushQueue();
    };

    ws.onmessage = (event) => {
      let msg: unknown;
      try {
        msg = JSON.parse(event.data as string);
      } catch {
        return;
      }
      if (!isRecord(msg)) return;

      // 应答（有 id）一律丢弃：本封装只关心推送
      if (msg.id !== undefined) return;
      if (typeof msg.method !== "string") return;
      if (msg.method === "ping") return; // 心跳

      dispatch(msg.method, isRecord(msg.params) ? msg.params : {});
    };

    ws.onclose = (event) => {
      ws = null;
      if (closedByUs) return;

      if (event.code === CLOSE_UNAUTHORIZED) {
        // 令牌失效，重连也没意义
        useUserStore.getState().logout();
        window.location.replace("/");
        return;
      }
      if (
        event.code === CLOSE_FORBIDDEN_ORIGIN ||
        event.code === CLOSE_DEVBOX_NOT_FOUND
      ) {
        console.warn("ws rejected by server", event.code, event.reason);
        return;
      }
      scheduleReconnect();
    };
  }

  return {
    connect: open,

    close() {
      closedByUs = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      queue.length = 0;
      ws?.close();
      ws = null;
    },

    sendWs(method, params) {
      rawSend(
        JSON.stringify({
          jsonrpc: "2.0",
          id: nextId++,
          method,
          params,
        }),
      );
    },

    subscribe(method, handler) {
      let set = handlers.get(method);
      if (!set) {
        set = new Set();
        handlers.set(method, set);
      }
      set.add(handler);
      return () => {
        set!.delete(handler);
        if (set!.size === 0) handlers.delete(method);
      };
    },
  };
}

/**
 * 会话级 WebSocket 客户端（JSON-RPC 2.0）。
 *
 * 一个 session 只许有一条连接（后端每个连接都会订阅一遍 devbox 并各跑一份心跳，
 * 多开则同一条推送会被重复收到），所以这里是一个手写的单连接封装，
 * 而不是每次调用都 `new WebSocket()`。
 *
 * 协议见 apps/api/src/app/api/ws/ws.md，前端只需要两条约定：
 *   - 有 `id` 的是应答：`call()` 等它，`sendWs()` 发出的不认领、直接丢弃
 *   - 没有 `id` 的是推送，按 `method` 分发给订阅者；`ping` 是心跳，静默忽略
 */

import { AGENT_API_URL } from "@/lib/agent-stream/agent-stream"
import { useUserStore } from "@/store/user"

const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 30_000

/** 握手被拒的关闭码：重连也没用 */
const CLOSE_UNAUTHORIZED = 4401
const CLOSE_FORBIDDEN_ORIGIN = 4403
const CLOSE_DEVBOX_NOT_FOUND = 4404

type Handler = (params: Record<string, unknown>) => void

/** `call()` 的默认应答超时。状态查询本身就是查库，正常几十毫秒内回。 */
const CALL_TIMEOUT_MS = 10_000

interface PendingCall {
  resolve: (result: unknown) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export interface WsClient {
  /** 发起连接；重复调用无副作用 */
  connect(): void
  /** 主动断开且不再重连（组件卸载时用） */
  close(): void
  /** 发一条 JSON-RPC 请求，不等应答 */
  sendWs(method: string, params: Record<string, unknown>): void
  /** 发一条 JSON-RPC 请求并等应答；超时/断开/返回 error 时 reject */
  call<T>(
    method: string,
    params: Record<string, unknown>,
    timeoutMs?: number
  ): Promise<T>
  /** 订阅某条推送；返回退订函数 */
  subscribe(method: string, handler: Handler): () => void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

/** http(s)://host → ws(s)://host/ws/devbox/{id}?token=… */
function buildUrl(devboxId: string, token: string | null): string {
  const wsBase = AGENT_API_URL.replace(/\/$/, "").replace(/^http/, "ws")
  const base = `${wsBase}/ws/devbox/${encodeURIComponent(devboxId)}`
  // 浏览器 WebSocket 构造函数设不了请求头，令牌只能走 query。
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

export function createWsClient({ devboxId }: { devboxId: string }): WsClient {
  let ws: WebSocket | null = null
  let closedByUs = false
  let reconnectAttempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let nextId = 1

  // CONNECTING 时 send() 会抛 InvalidStateError，先排队、连上后一起发（ws.md 做法 A）。
  const queue: string[] = []

  const handlers = new Map<string, Set<Handler>>()
  // 等应答的请求（`call()` 发起的），按 JSON-RPC id 索引。
  const pending = new Map<number, PendingCall>()

  function settlePending(id: number, msg: Record<string, unknown>) {
    const entry = pending.get(id)
    if (!entry) return // sendWs 发出的请求不认领应答
    pending.delete(id)
    clearTimeout(entry.timer)
    if (isRecord(msg.error)) {
      const message =
        typeof msg.error.message === "string"
          ? msg.error.message
          : "ws 请求失败"
      entry.reject(new Error(message))
    } else {
      entry.resolve(msg.result)
    }
  }

  /** 连接结束时让所有等待中的调用失败，否则它们的 promise 永远悬着。 */
  function rejectAllPending(reason: string) {
    for (const [id, entry] of pending) {
      pending.delete(id)
      clearTimeout(entry.timer)
      entry.reject(new Error(reason))
    }
  }

  function rawSend(text: string) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(text)
    } else {
      queue.push(text)
    }
  }

  function flushQueue() {
    if (!ws) return
    while (queue.length && ws.readyState === WebSocket.OPEN) {
      ws.send(queue.shift()!)
    }
  }

  function dispatch(method: string, params: Record<string, unknown>) {
    const set = handlers.get(method)
    if (!set) return // 不认识的 method 静默忽略——后端随时可能加新推送
    for (const handler of set) {
      try {
        handler(params)
      } catch (error) {
        // 单个订阅者报错不能拖垮连接和其余订阅者
        console.error(`ws handler error: ${method}`, error)
      }
    }
  }

  function scheduleReconnect() {
    if (closedByUs || reconnectTimer) return
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** reconnectAttempt,
      RECONNECT_MAX_MS
    )
    reconnectAttempt += 1
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      open()
    }, delay)
  }

  function open() {
    if (closedByUs) return
    if (ws && ws.readyState <= WebSocket.OPEN) return

    // 每次建连时现读令牌：persist 回填晚于首屏挂载，捕获进闭包会拿到 null，
    // 那样握手会被 4401 拒掉。
    const token = useUserStore.getState().token
    if (!token) {
      console.warn("ws: 没有令牌，跳过连接")
      return
    }

    // 用局部引用：StrictMode 下旧连接的 onclose 可能晚于新连接建立才触发，
    // 若直接写外层 ws，会把新连接置空并多排一次重连。
    const socket = new WebSocket(buildUrl(devboxId, token))
    ws = socket

    socket.onopen = () => {
      reconnectAttempt = 0
      flushQueue()
    }

    socket.onmessage = (event) => {
      if (ws !== socket) return // 已被替换的旧连接，丢弃它的消息
      let msg: unknown
      try {
        msg = JSON.parse(event.data as string)
      } catch {
        return
      }
      if (!isRecord(msg)) return

      // 应答（有 id）：只交给 call() 发起的请求，其余照旧丢弃
      if (msg.id !== undefined) {
        if (typeof msg.id === "number") settlePending(msg.id, msg)
        return
      }
      if (typeof msg.method !== "string") return
      if (msg.method === "ping") return // 心跳

      dispatch(msg.method, isRecord(msg.params) ? msg.params : {})
    }

    socket.onclose = (event) => {
      if (ws !== socket) return // 已被替换的旧连接，它的关闭不影响当前连接
      ws = null
      rejectAllPending("ws 连接已关闭")
      if (closedByUs) return

      if (event.code === CLOSE_UNAUTHORIZED) {
        // 令牌失效，重连也没意义
        useUserStore.getState().logout()
        window.location.replace("/")
        return
      }
      if (
        event.code === CLOSE_FORBIDDEN_ORIGIN ||
        event.code === CLOSE_DEVBOX_NOT_FOUND
      ) {
        console.warn("ws rejected by server", event.code, event.reason)
        return
      }
      scheduleReconnect()
    }
  }

  return {
    // StrictMode 下 effect 会「挂载→清理→再挂载」，清理里的 close() 把
    // closedByUs 置 true 后如果不复位，第二次挂载的 connect() 会被 open() 首行挡住，
    // 整页 ws 从此连不上。所以重新连接前先解除主动关闭标记。
    connect() {
      closedByUs = false
      open()
    },

    close() {
      closedByUs = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      queue.length = 0
      ws?.close()
      ws = null
    },

    sendWs(method, params) {
      rawSend(
        JSON.stringify({
          jsonrpc: "2.0",
          id: nextId++,
          method,
          params,
        })
      )
    },

    call<T>(
      method: string,
      params: Record<string, unknown>,
      timeoutMs = CALL_TIMEOUT_MS
    ): Promise<T> {
      const id = nextId++
      const text = JSON.stringify({
        jsonrpc: "2.0",
        id,
        method,
        params,
      })

      return new Promise<T>((resolve, reject) => {
        // 断开时 rawSend 只会排队，超时由 timer 兜底——promise 不会悬着。
        const timer = setTimeout(() => {
          pending.delete(id)
          reject(new Error(`ws 请求超时: ${method}`))
        }, timeoutMs)
        pending.set(id, {
          resolve: resolve as (result: unknown) => void,
          reject,
          timer,
        })
        rawSend(text)
      })
    },

    subscribe(method, handler) {
      let set = handlers.get(method)
      if (!set) {
        set = new Set()
        handlers.set(method, set)
      }
      set.add(handler)
      return () => {
        set!.delete(handler)
        if (set!.size === 0) handlers.delete(method)
      }
    },
  }
}

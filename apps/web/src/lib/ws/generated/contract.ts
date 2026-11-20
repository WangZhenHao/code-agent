// 由 apps/api/scripts/gen_ws_contract.py 生成，不要手改。
// 重新生成：make gen-ws（改了 ws/core/events.py 或 @rpc_method 的模型之后）。

export type WsPushEvent = "web.server_status_changed" | "web.project_update"

export interface WsPushParams {
  "web.server_status_changed": {
    preview: {
      status: string
      preview_url: string | null
      preview_enabled: boolean
    }
  }
  "web.project_update": {
    title: string
    description: string
  }
}

export const WS_PUSH_EVENTS: readonly WsPushEvent[] = [
  "web.server_status_changed",
  "web.project_update",
]

export type WsRequestMethod = "file.read" | "file.stat" | "web.preview_heartbeat" | "web.preview_status" | "web.sandbox_status"

export interface WsRequestParams {
  "file.read": {
    path: string
  }
  "file.stat": {
    path: string
  }
  "web.preview_heartbeat": Record<string, never>
  "web.preview_status": Record<string, never>
  "web.sandbox_status": Record<string, never>
}

export interface WsRequestResult {
  "file.read": {
    content: string
    encoding: string
    size: number
    mtime: number
    ctime: number
    totalLine: number
  }
  "file.stat": {
    path: string
    size: number
    mtime: number
    ctime: number
    isDirectory: boolean
    isFile: boolean
    isSymbolicLink: boolean
    permissions: string
    children: {
      name: string
      isDirectory: boolean
      size: number
      mtime: number
    }[] | null
  }
  "web.preview_heartbeat": {
    session_id: string
    extended: boolean
  }
  "web.preview_status": {
    status: string
    preview_url: string | null
    preview_enabled: boolean
  }
  "web.sandbox_status": {
    status: string
    preview_url: string | null
    preview_enabled: boolean
  }
}

export const WS_REQUEST_METHODS: readonly WsRequestMethod[] = [
  "file.read",
  "file.stat",
  "web.preview_heartbeat",
  "web.preview_status",
  "web.sandbox_status",
]

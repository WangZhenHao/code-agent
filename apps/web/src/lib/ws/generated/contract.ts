// 由 apps/api/scripts/gen_ws_contract.py 生成，不要手改。
// 重新生成：make gen-ws（改了 apps/api/src/app/api/ws/core/events.py 之后）。

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

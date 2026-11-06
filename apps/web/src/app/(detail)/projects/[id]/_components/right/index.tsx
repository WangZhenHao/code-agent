"use client"

import { useState } from "react"

import { useWs, useWsEvent } from "@/components/providers/ws-provider"

import Header from "./header"
import Preview from "./preview"
import PreviewOptions from "./preview-options"

/**
 * 预览面板。数据来源是后端推送 `web.server_status_changed`
 * （params.preview 与 `preview.status` 应答同形状）；刚连上时可以发一次
 * `preview.status` 补齐当前快照——推送是尽力而为，丢了不会重发。
 *
 * 是否可用只看 `preview_enabled`：`status` 的取值（idle/building/running/failed）
 * 是后端内部状态，前端不该逐个认，后端已经把它折算成布尔了。
 */
const Right = () => {
  const { sendWs } = useWs()
  const [previewEnabled, setPreviewEnabled] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  useWsEvent("web.server_status_changed", (params) => {
    const preview = params.preview
    if (preview && typeof preview === "object") {
      const p = preview as Record<string, unknown>
      setPreviewEnabled(p.preview_enabled === true)
      setPreviewUrl(typeof p.preview_url === "string" ? p.preview_url : null)
    }
  })

  return (
    <div className="flex min-w-0 flex-1 flex-col pr-2 pb-2">
      <Header />
      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border">
        <PreviewOptions
          url={previewUrl}
          onRefresh={() => sendWs("preview.status", {})}
        />
        <Preview enabled={previewEnabled} url={previewUrl} />
      </div>
    </div>
  )
}

export default Right

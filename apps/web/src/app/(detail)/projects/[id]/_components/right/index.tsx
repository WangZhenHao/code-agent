"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { useWs, useWsEvent } from "@/components/providers/ws-provider"

import Header from "./header"
import Preview from "./preview"
import PreviewOptions from "./preview-options"

/** 续期间隔。后端 ttl 30 分钟、回收器 5 分钟扫一次，5 分钟一拍留足余量。 */
const KEEPALIVE_MS = 5 * 60 * 1000

interface PreviewSnapshot {
  status?: string
  preview_url?: string | null
  preview_enabled?: boolean
}

/**
 * 预览面板。数据来源有两个：
 *   - 推送 `web.server_status_changed`（params.preview 与应答同形状）
 *   - 主动请求 `sandbox_status`：进入页面时拉一次快照，后端顺带把沙箱和 dev
 *     server 拉起来；推送是尽力而为，丢了不会重发，所以还需要这第一次查询
 *
 * 是否可用只看 `preview_enabled`：`status` 的取值（idle/building/running/failed）
 * 是后端内部状态，前端不该逐个认，后端已经把它折算成布尔了。
 */
const Right = () => {
  const { call } = useWs()
  const [previewEnabled, setPreviewEnabled] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  // 上一拍心跳还没回来时跳过本轮，避免冷启动/断网时堆请求
  const heartbeatInFlight = useRef(false)

  // 入参收 unknown 再自己收窄：推送和应答都是外部数据，只有一个来源时断言
  // 会被 lint 判成多余，索性把这个边界收在一处。
  const applySnapshot = useCallback((snapshot: unknown) => {
    if (!snapshot || typeof snapshot !== "object") return
    const s = snapshot as Record<string, unknown>
    setPreviewEnabled(s.preview_enabled === true)
    setPreviewUrl(typeof s.preview_url === "string" ? s.preview_url : null)
  }, [])

  useWsEvent("web.server_status_changed", (params) => {
    applySnapshot(params.preview)
  })

  const refresh = useCallback(async () => {
    try {
      applySnapshot(await call<PreviewSnapshot>("sandbox_status", {}))
    } catch (error) {
      // 首次查询失败不致命：推送到达时仍会补上状态，续期下一拍也会再试
      console.warn("sandbox_status 请求失败", error)
    }
  }, [applySnapshot, call])

  useEffect(() => {
    // 首次进入拉一次快照。放进 setTimeout：直接在 effect 体里 setState 会触发
    // 级联渲染（react-hooks/set-state-in-effect）。
    const initial = setTimeout(() => void refresh(), 0)

    const timer = setInterval(() => {
      if (heartbeatInFlight.current) return
      heartbeatInFlight.current = true
      call<{ extended?: boolean }>("preview.heartbeat", {})
        .catch((error: unknown) => {
          console.warn("preview.heartbeat 请求失败", error)
        })
        .finally(() => {
          heartbeatInFlight.current = false
        })
    }, KEEPALIVE_MS)

    return () => {
      clearTimeout(initial)
      clearInterval(timer)
    }
  }, [call, refresh])

  return (
    <div className="flex min-w-0 flex-1 flex-col pr-2 pb-2">
      <Header />
      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border">
        <PreviewOptions onRefresh={() => void refresh()} />
        <Preview enabled={previewEnabled} url={previewUrl} />
      </div>
    </div>
  )
}

export default Right

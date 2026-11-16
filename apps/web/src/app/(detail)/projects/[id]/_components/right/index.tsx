"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { useWs, useWsEvent } from "@/components/providers/ws-provider"
import type { WsPushParams } from "@/lib/ws/generated/contract"

import Header from "./header"
import Preview from "./preview"
import PreviewOptions from "./preview-options"
import { useProjectDetailStore } from "@/store/project-detail"

/** 续期间隔。后端 ttl 30 分钟、回收器 5 分钟扫一次，5 分钟一拍留足余量。 */
const KEEPALIVE_MS = 2 * 60 * 1000

type PreviewSnapshot = WsPushParams["web.server_status_changed"]["preview"]

const Right = () => {
  const { call } = useWs()
  const [previewEnabled, setPreviewEnabled] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  // 上一拍心跳还没回来时跳过本轮，避免冷启动/断网时堆请求
  const heartbeatInFlight = useRef(false)
  const { updateField } = useProjectDetailStore()

  const applySnapshot = useCallback(
    ({ preview_url, preview_enabled }: PreviewSnapshot) => {
      setPreviewEnabled(preview_enabled)
      setPreviewUrl(preview_url)
      updateField({ preview_url })
    },
    [updateField]
  )

  useWsEvent("web.server_status_changed", (params) => {
    applySnapshot(params.preview)
  })

  // 标题/描述是建会话之后模型异步生成、落库后才推过来的：create_chat 的响应里
  // 还是空串，所以只能靠这条推送补进 store，header 从 store 读。
  useWsEvent("web.project_update", ({ title, description }) => {
    updateField({ title, description })
  })

  const refresh = useCallback(async () => {
    try {
      applySnapshot(await call<PreviewSnapshot>("web.sandbox_status", {}))
    } catch (error) {
      // 首次查询失败不致命：推送到达时仍会补上状态，续期下一拍也会再试
      console.warn("web.sandbox_status 请求失败", error)
    }
  }, [applySnapshot, call])

  useEffect(() => {
    // 首次进入拉一次快照。放进 setTimeout：直接在 effect 体里 setState 会触发
    // 级联渲染（react-hooks/set-state-in-effect）。
    const initial = setTimeout(() => void refresh(), 0)

    const timer = setInterval(() => {
      if (heartbeatInFlight.current) return
      heartbeatInFlight.current = true
      call<{ devbox_id: string; extended: boolean }>(
        "web.preview_heartbeat",
        {}
      )
        .catch((error: unknown) => {
          console.warn("web.preview_heartbeat 请求失败", error)
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

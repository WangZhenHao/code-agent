"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { useWs, useWsEvent } from "@/components/providers/ws-provider"
import type { WsPushParams } from "@/lib/ws/generated/contract"

import PreviewLoading from "./preview-loading"
import PreviewOptions from "./preview-options"
import { useProjectDetailStore } from "@/store/project-detail"

/** 续期间隔。后端 ttl 30 分钟、回收器 5 分钟扫一次，5 分钟一拍留足余量。 */
const KEEPALIVE_MS = 2 * 60 * 1000

type PreviewSnapshot = WsPushParams["web.server_status_changed"]["preview"]

/**
 * 预览区。`enabled`（后端 `preview_enabled`）且拿到 `url` 时渲染 iframe，
 * 否则显示占位（点阵背景 + 快捷键提示）。
 */
const PreviewFrame = ({
  enabled,
  url,
}: {
  enabled: boolean
  url?: string | null
}) => {
  if (url && enabled) {
    return (
      <div className="min-h-0 flex-1 overflow-hidden border-t bg-background">
        <iframe src={url} title="预览" className="size-full border-0" />
      </div>
    )
  }

  return <PreviewLoading ready={enabled} />
}

/**
 * 右侧预览面板：顶栏 + 工具栏 + 预览区。
 * 负责拉取预览状态、跟随 WS 推送更新、维持沙箱续期心跳。
 */
const Preview = () => {
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
      call<{ session_id: string; extended: boolean }>(
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
    <>
      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border">
        <PreviewOptions onRefresh={() => void refresh()} />
        <PreviewFrame enabled={previewEnabled} url={previewUrl} />
      </div>
    </>
  )
}

export default Preview

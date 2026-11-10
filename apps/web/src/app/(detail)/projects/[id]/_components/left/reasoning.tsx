"use client"

import { useEffect, useRef, useState } from "react"

import { BrainIcon, ChevronRight } from "lucide-react"

import Markdown from "@/components/custom/markdown"
import { cn } from "@/lib/utils"

/**
 * 模型的思考过程（reasoning）。流式时默认展开，这条消息结束后自动折叠；
 * 结束后用户可以再点开看。渲染对齐 ./tool-call 的折叠行。
 *
 * 只在 `streaming` 由 true 变 false 的那一刻收起，流式期间用户手动收起
 * 不会被重新撑开——每次 delta 都会重渲染，但组件状态不受影响。
 */
export const Reasoning = ({
  text,
  streaming,
}: {
  text: string
  streaming: boolean
}) => {
  const [open, setOpen] = useState(streaming)
  const wasStreaming = useRef(streaming)

  useEffect(() => {
    if (wasStreaming.current && !streaming) setOpen(false)
    wasStreaming.current = streaming
  }, [streaming])

  if (!text) return null

  return (
    <div className="mb-1 rounded-md border bg-muted/30 text-foreground">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <ChevronRight
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-90"
          )}
        />
        <BrainIcon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="shrink-0 text-sm font-medium whitespace-nowrap">
          思考过程
        </span>
        <span className="truncate font-mono text-xs text-muted-foreground">
          {text.length} 字
        </span>
      </button>
      {open ? (
        <div className="max-h-60 overflow-auto border-t px-3 py-2 text-xs text-muted-foreground">
          <Markdown text={text} />
        </div>
      ) : null}
    </div>
  )
}

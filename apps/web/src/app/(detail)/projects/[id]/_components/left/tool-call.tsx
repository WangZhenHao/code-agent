"use client"

import { useState } from "react"

import { ChevronRight } from "lucide-react"

import Markdown from "@/components/custom/markdown"
import type { ToolMessage } from "@langchain/core/messages"
import { cn } from "@/lib/utils"

/**
 * 一次工具调用的展示：一行「工具名 + 参数摘要」，点开显示对应的工具结果。
 *
 * 结果按 `tool_call_id` 从 `toolResults` 取——tool_calls 本身只带参数，
 * 输出来自另一条 ToolMessage（历史里的 `type: "tool"` part 或 SSE 的实时消息）。
 * 流式期间结果可能还没到，展开就是「（暂无结果）」。
 */
export const ToolCall = ({
  name,
  args,
  result,
}: {
  name: string
  args: Record<string, unknown>
  result?: ToolMessage
}) => {
  const [open, setOpen] = useState(false)

  return (
    <li className="border-l-2 border-border pl-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-1 text-left hover:text-foreground"
      >
        <ChevronRight
          className={cn(
            "size-3 shrink-0 transition-transform",
            open && "rotate-90"
          )}
        />
        <span className="shrink-0 font-medium">{name}</span>
        <span className="truncate font-mono">{toolCallSummary(args)}</span>
      </button>
      {open ? (
        <div className="mt-1 max-h-80 overflow-auto">
          <Markdown text={toCodeBlock(result?.text || "（暂无结果）")} />
        </div>
      ) : null}
    </li>
  )
}

/**
 * 工具输出是纯文本（shell stdout / 文件内容），套进围栏代码块再交给 Markdown，
 * 这样换行、空白都能原样保留，长行也不会撑破气泡（markdown 的 pre 自带横向滚动）。
 * 围栏长度按内容里最长的反引号串加一取，避免输出里自带 ``` 把块提前闭合。
 */
const toCodeBlock = (text: string) => {
  const runs: string[] = text.match(/`+/g) ?? []
  const longest = runs.reduce((max, run) => Math.max(max, run.length), 0)
  const fence = "`".repeat(Math.max(3, longest + 1))
  return `${fence}\n${text}\n${fence}`
}

/**
 * 工具参数的一行摘要：bash 显示命令，文件类工具显示路径/模式，
 * 其余按 JSON 截断。流式期间参数可能还没到齐，取不到就退回空串。
 */
const SummaryKeys = ["command", "file_path", "pattern", "path"]

const toolCallSummary = (args: Record<string, unknown>) => {
  const key = SummaryKeys.find((key) => typeof args[key] === "string")
  if (key) return String(args[key])
  try {
    return truncateText(JSON.stringify(args), 80)
  } catch {
    return ""
  }
}

const truncateText = (text: string, max: number) =>
  text.length > max ? `${text.slice(0, max)}…` : text

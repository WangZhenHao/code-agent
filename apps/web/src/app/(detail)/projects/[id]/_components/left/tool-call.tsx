"use client"

import { useState } from "react"

import {
  ChevronRight,
  FileIcon,
  FileSearchIcon,
  SparklesIcon,
  SquareTerminalIcon,
  TextSearchIcon,
  WrenchIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import Markdown from "@/components/custom/markdown"
import { cn } from "@/lib/utils"
import type { ToolMessage } from "@langchain/core/messages"

/**
 * 一次工具调用的展示：一行「图标 + 工具标签 + 参数摘要 + 状态」，
 * 点开显示调用参数和工具结果。
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
  const meta = TOOL_META[name]
  const Icon = meta?.icon ?? WrenchIcon
  const label = meta?.label ?? name
  const summary = meta && !open ? meta.summary(args) : ""
  const status = result?.status

  return (
    <li className="rounded-md border bg-muted/30 text-foreground">
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
        <Icon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="shrink-0 text-sm font-medium whitespace-nowrap">
          {label}
        </span>
        {summary ? (
          <span className="truncate font-mono text-xs text-muted-foreground">
            {summary}
          </span>
        ) : null}
        {status ? (
          <span className="ml-auto flex shrink-0 items-center gap-1.5">
            <Badge
              variant={status === "error" ? "destructive" : "outline"}
              className="font-normal"
            >
              {status === "error" ? "失败" : "成功"}
            </Badge>
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="space-y-2 border-t px-3 py-2">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              调用参数
            </div>
            <pre className="max-h-48 overflow-auto rounded bg-background p-2 font-mono text-xs whitespace-pre-wrap">
              {formatArgs(args)}
            </pre>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              返回结果
            </div>
            <div className="max-h-60 overflow-auto">
              <Markdown
                text={toCodeBlock(
                  truncateText(result?.text || "（暂无结果）"),
                  resultLanguage(name, args)
                )}
              />
            </div>
          </div>
        </div>
      ) : null}
    </li>
  )
}

const asString = (value: unknown) => (typeof value === "string" ? value : "")

/** 工具展示：名称 → 中文标签、图标与行内参数摘要，名称与后端 `@tool` 注册的一致 */
const TOOL_META: Record<
  string,
  {
    label: string
    icon: typeof FileIcon
    summary: (args: Record<string, unknown>) => string
  }
> = {
  read_file: {
    label: "读取文件",
    icon: FileIcon,
    summary: (a) => asString(a.file_path),
  },
  write_file: {
    label: "写入文件",
    icon: FileIcon,
    summary: (a) => asString(a.file_path),
  },
  edit_file: {
    label: "编辑文件",
    icon: FileIcon,
    summary: (a) => asString(a.file_path),
  },
  grep: {
    label: "搜索内容",
    icon: TextSearchIcon,
    summary: (a) => asString(a.pattern) || asString(a.path),
  },
  glob: {
    label: "查找文件",
    icon: FileSearchIcon,
    summary: (a) => asString(a.pattern),
  },
  bash: {
    label: "执行命令",
    icon: SquareTerminalIcon,
    summary: (a) => asString(a.command).split("\n")[0],
  },
  read_skill: {
    label: "读取技能",
    icon: SparklesIcon,
    summary: (a) => asString(a.name),
  },
}

/** 参数还没流式到齐时是空对象，仍然展示成 `{}`，避免展开后一片空白。 */
const formatArgs = (args: Record<string, unknown>) =>
  JSON.stringify(args, null, 2)

const truncateText = (text: string, max = 4000) =>
  text.length > max
    ? `${text.slice(0, max)}\n…（已截断，共 ${text.length} 字）`
    : text

/**
 * 工具输出是纯文本（shell stdout / 文件内容），套进围栏代码块再交给 Markdown，
 * 这样换行、空白都能原样保留，长行也不会撑破气泡（markdown 的 pre 自带横向滚动）。
 * 围栏长度按内容里最长的反引号串加一取，避免输出里自带 ``` 把块提前闭合。
 * `language` 是 highlight.js 的语言名，没有就留空、按纯文本展示。
 */
const toCodeBlock = (text: string, language?: string) => {
  const runs: string[] = text.match(/`+/g) ?? []
  const longest = runs.reduce((max, run) => Math.max(max, run.length), 0)
  const fence = "`".repeat(Math.max(3, longest + 1))
  return `${fence}${language ?? ""}\n${text}\n${fence}`
}

/**
 * 工具结果该按什么语言高亮：bash 的输出就是 shell 脚本，
 * 文件类工具看读写路径的扩展名，搜索类工具的输出是普通文本、不上色。
 *
 * 扩展名直接当语言名用——lowlight 注册了 ts/tsx/py/yml/md/h 这类别名，
 * 认不出的会被 rehype-highlight 的 `ignoreMissing` 忽略、退回纯文本。
 */
const resultLanguage = (name: string, args: Record<string, unknown>) => {
  if (name === "bash") return "bash"
  const path = asString(args.file_path) || asString(args.path)
  if (!path) return undefined
  const base = path.split("/").pop() ?? ""
  return base.includes(".") ? base.split(".").pop()?.toLowerCase() : undefined
}

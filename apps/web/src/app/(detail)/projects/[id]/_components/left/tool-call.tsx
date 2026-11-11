"use client"

import { useState } from "react"

import { isAxiosError } from "axios"
import {
  ChevronRight,
  FileIcon,
  FileSearchIcon,
  SparklesIcon,
  SquareTerminalIcon,
  TextSearchIcon,
  WrenchIcon,
} from "lucide-react"

import { useThreadToolCallAgentsSessionIdToolsToolCallIdGet } from "@/api/generated/agent/agent"
import { Badge } from "@/components/ui/badge"
import Markdown from "@/components/custom/markdown"
import { cn } from "@/lib/utils"

/**
 * 一次工具调用的展示：一行「图标 + 工具标签 + 参数摘要 + 状态」，
 * 点开显示调用参数和工具结果。
 *
 * 结果不再随 SSE / 历史消息传给前端（工具输出可能长达 30k 字符），
 * 而是按 `tool_call_id` 查 `GET /agents/{id}/tools/{tool_call_id}`。
 * 只在展开时请求，避免一屏几十个卡片同时拉取。
 */
export const ToolCall = ({
  sessionId,
  toolCallId,
  name,
  args,
}: {
  sessionId: string
  toolCallId?: string
  name: string
  args: Record<string, unknown>
}) => {
  const [open, setOpen] = useState(false)
  const meta = TOOL_META[name]
  const Icon = meta?.icon ?? WrenchIcon
  const label = meta?.label ?? name
  const summary = meta && !open ? meta.summary(args) : ""

  const toolCallQuery = useThreadToolCallAgentsSessionIdToolsToolCallIdGet(
    sessionId,
    toolCallId ?? "",
    {
      query: {
        enabled: open && Boolean(toolCallId),
        // running 时轮询；拿到终态就停。interrupted / error 也不再轮询。
        refetchInterval: (query) =>
          query.state.data?.status === "running" ? 1500 : false,
        // 工具刚结束时可能还是 running，别把那次结果当长期缓存。
        staleTime: 0,
        // 404 = 这行还没写进库（工具刚发起），当作「尚无结果」重试一次。
        retry: (failureCount, error) =>
          isAxiosError(error) &&
          error.response?.status === 404 &&
          failureCount < 3,
        retryDelay: 1500,
      },
    }
  )

  const result = toolCallQuery.data
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
        {open && status ? (
          <span className="ml-auto flex shrink-0 items-center gap-1.5">
            <Badge
              variant={status === "error" ? "destructive" : "outline"}
              className="font-normal"
            >
              {STATUS_LABEL[status] ?? status}
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
              {/* 流里的 content 长字段已被后端脱敏；接口的 input 才是完整参数。 */}
              {formatArgs(
                (result?.input as Record<string, unknown> | undefined) ?? args
              )}
            </pre>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              返回结果
            </div>
            <div className="max-h-60 overflow-auto">
              {result ? (
                <Markdown
                  text={toCodeBlock(
                    result.output || "（暂无结果）",
                    resultLanguage(name, args)
                  )}
                />
              ) : (
                <div className="text-xs text-muted-foreground">
                  {toolCallQuery.isError ? "（暂无结果）" : "加载中…"}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </li>
  )
}

const STATUS_LABEL: Record<string, string> = {
  running: "执行中",
  success: "成功",
  error: "失败",
  interrupted: "已中断",
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

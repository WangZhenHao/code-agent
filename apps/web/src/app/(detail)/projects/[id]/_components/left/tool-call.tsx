"use client"

import { useState } from "react"

import { isAxiosError } from "axios"
import {
  ChevronRight,
  FileIcon,
  FilePenIcon,
  FileSearchIcon,
  SparklesIcon,
  SquareTerminalIcon,
  TextSearchIcon,
  WrenchIcon,
} from "lucide-react"

import { useThreadToolCallAgentsSessionIdToolsToolCallIdGet } from "@/api/generated/agent/agent"
import { Badge } from "@/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

import { fileLanguage, resultLanguage, ToolCodeBlock } from "./tool-code-block"
import { ToolDiffBlock } from "./tool-diff-block"

/**
 * 一次工具调用的展示：一行「图标 + 目标（路径 / 命令）」，点开显示结果。
 *
 * 结果不再随 SSE / 历史消息传给前端（工具输出可能长达 30k 字符），
 * 而是按 `tool_call_id` 查 `GET /agents/{id}/tools/{tool_call_id}`。
 * 只在展开时请求，避免一屏几十个卡片同时拉取。
 *
 * 还没有工具名的调用就是仍在执行中：这时显示 loading 且不可展开——
 * 此时库里还没有结果，展开只会看到空壳。
 */
export const ToolCall = ({
  sessionId,
  toolCallId,
  name,
  args,
}: {
  sessionId: string
  toolCallId?: string
  /** 工具名，流式传输中尚未到达时为空字符串，表示仍在调用 */
  name: string
  args: Record<string, unknown>
}) => {
  const [open, setOpen] = useState(false)
  const running = !name
  const meta = TOOL_META[name]
  const Icon = meta?.icon ?? WrenchIcon
  const target = meta ? meta.target(args) : name
  const expanded = open && !running

  const toolCallQuery = useThreadToolCallAgentsSessionIdToolsToolCallIdGet(
    sessionId,
    toolCallId ?? "",
    {
      query: {
        enabled: expanded && Boolean(toolCallId),
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
  // 流里的长字段被后端脱敏，接口的 input 才是完整参数。
  const fullArgs = mergeArgs(args, result?.input)

  return (
    <Collapsible
      open={expanded}
      onOpenChange={(value) => {
        if (!running) setOpen(value)
      }}
      className={cn(
        "overflow-hidden rounded-md transition-colors",
        expanded && "border bg-card"
      )}
    >
      <CollapsibleTrigger
        disabled={running}
        title={meta?.label ?? name}
        className={cn(
          "flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors disabled:cursor-default",
          !expanded && "hover:bg-muted/60"
        )}
      >
        {running ? (
          <Spinner className="size-3.5 shrink-0" />
        ) : (
          <Icon className="size-3.5 shrink-0" />
        )}
        <span className="shrink-0">{meta?.label ?? name}</span>
        <span className="truncate font-mono" title={target}>
          {target}
        </span>
        {status === "error" || status === "interrupted" ? (
          <Badge variant="destructive" className="ml-auto shrink-0 font-normal">
            {STATUS_LABEL[status]}
          </Badge>
        ) : (
          <ChevronRight
            className={cn(
              "ml-auto size-3.5 shrink-0 transition-transform",
              expanded && "rotate-90"
            )}
          />
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t px-2 py-2 [&_pre]:mt-0 [&_pre]:rounded-none [&_pre]:border-0 [&_pre]:bg-transparent [&_pre]:p-1">
          <ToolResult
            name={name}
            args={fullArgs}
            output={result?.output ?? null}
            loading={toolCallQuery.isPending && !result}
            failed={toolCallQuery.isError}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

const STATUS_LABEL: Record<string, string> = {
  running: "执行中",
  success: "成功",
  error: "失败",
  interrupted: "已中断",
}

const asString = (value: unknown) => (typeof value === "string" ? value : "")

/** 流式 args + 接口 input，后者为准；input 不是对象时只回退到 args。 */
const mergeArgs = (
  args: Record<string, unknown>,
  input: unknown
): Record<string, unknown> => {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return args
  }
  return { ...args, ...(input as Record<string, unknown>) }
}

/** 展开后的正文：按工具类型选展示方式，写文件/编辑要给人看的不是工具返回值。 */
const ToolResult = ({
  name,
  args,
  output,
  loading,
  failed,
}: {
  name: string
  args: Record<string, unknown>
  output: string | null
  loading: boolean
  failed: boolean
}) => {
  if (name === "write_file") {
    const content = asString(args.content)
    return content ? (
      <ToolCodeBlock
        code={content}
        language={fileLanguage(args)}
        className="max-h-80"
      />
    ) : (
      <Placeholder loading={loading} failed={failed} />
    )
  }

  if (name === "edit_file") {
    const oldString = asString(args.old_string)
    const newString = asString(args.new_string)
    return oldString || newString ? (
      <div className="max-h-80 overflow-auto rounded bg-background">
        <ToolDiffBlock oldString={oldString} newString={newString} />
      </div>
    ) : (
      <Placeholder loading={loading} failed={failed} />
    )
  }

  if (loading) return <Placeholder loading failed={false} />
  return output ? (
    <ToolCodeBlock
      code={output}
      language={resultLanguage(name, args)}
      className="max-h-60"
    />
  ) : (
    <Placeholder loading={false} failed={failed} />
  )
}

const Placeholder = ({
  loading,
  failed,
}: {
  loading: boolean
  failed: boolean
}) => (
  <div className="text-xs text-muted-foreground">
    {loading ? "加载中…" : failed ? "（获取结果失败）" : "（暂无结果）"}
  </div>
)

/** 工具展示：名称 → 中文标签、图标与行内目标文本，名称与后端 `@tool` 注册的一致 */
const TOOL_META: Record<
  string,
  {
    label: string
    icon: typeof FileIcon
    target: (args: Record<string, unknown>) => string
  }
> = {
  read_file: {
    label: "读取文件",
    icon: FileIcon,
    target: (a) => asString(a.file_path),
  },
  write_file: {
    label: "写入文件",
    icon: FilePenIcon,
    target: (a) => asString(a.file_path),
  },
  edit_file: {
    label: "编辑文件",
    icon: FilePenIcon,
    target: (a) => asString(a.file_path),
  },
  grep: {
    label: "搜索内容",
    icon: TextSearchIcon,
    target: (a) => asString(a.pattern) || asString(a.path),
  },
  glob: {
    label: "查找文件",
    icon: FileSearchIcon,
    target: (a) => asString(a.pattern),
  },
  bash: {
    label: "执行命令",
    icon: SquareTerminalIcon,
    target: (a) => asString(a.command).split("\n")[0],
  },
  read_skill: {
    label: "读取技能",
    icon: SparklesIcon,
    target: (a) => asString(a.name),
  },
}

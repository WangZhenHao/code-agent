"use client"

import { useState } from "react"

import { CheckIcon, ChevronRight, CircleIcon } from "lucide-react"

import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

import type { TodoItem } from "../hook/use-todos"

/**
 * Agent 内部 todo 的进度面板：默认收起成一行摘要，点开是完整清单。
 *
 * 常驻在输入框上方（滚动区之外），所以长任务进行到一半时用户往上翻了历史、
 * 也还能看到当前进度。清单为空时不渲染——模型判断任务简单、没调
 * `write_todos` 时不该出现一个空面板。
 */
export const TodoPanel = ({ todos }: { todos: TodoItem[] }) => {
  const [open, setOpen] = useState(false)

  if (todos.length === 0) return null

  const done = todos.filter((todo) => todo.status === "completed").length
  const current = todos.find((todo) => todo.status === "in_progress")?.content
  const allDone = done === todos.length

  return (
    <div className="my-2 shrink-0 rounded-md border bg-muted/30 text-foreground">
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
        <span className="shrink-0 text-sm font-medium whitespace-nowrap">
          进度 {done}/{todos.length}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {allDone ? "任务已完成" : current ? `正在做：${current}` : ""}
        </span>
      </button>
      {open ? (
        <ul className="space-y-1.5 border-t px-3 py-2 text-xs">
          {todos.map((todo, index) => (
            <li
              key={`${index}-${todo.content}`}
              className="flex items-start gap-2"
            >
              <StatusIcon status={todo.status} />
              <span
                className={cn(
                  "leading-5",
                  todo.status === "completed" &&
                    "text-muted-foreground line-through",
                  todo.status === "in_progress" && "font-medium"
                )}
              >
                {todo.content}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

const StatusIcon = ({ status }: { status: TodoItem["status"] }) => {
  if (status === "completed") {
    return (
      <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
    )
  }
  if (status === "in_progress") {
    return <Spinner className="mt-0.5 size-3.5 shrink-0" />
  }
  return (
    <CircleIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/60" />
  )
}

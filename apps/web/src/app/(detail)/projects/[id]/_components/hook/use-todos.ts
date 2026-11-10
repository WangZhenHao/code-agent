"use client"

import { useMemo } from "react"

import { type BaseMessage } from "@langchain/core/messages"
import { useExtension, type useStreamContext } from "@langchain/react"

/**
 * 本轮子任务清单。形状与后端 `langchain.agents.middleware.todo.Todo` 一致，
 * 也与模型传给 `write_todos` 的 `args.todos` 一致。
 */
export type TodoItem = {
  content: string
  status: "pending" | "in_progress" | "completed"
}

type TodosPayload = { todos: TodoItem[] }

const isTodoItem = (value: unknown): value is TodoItem =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as { content?: unknown }).content === "string" &&
  ["pending", "in_progress", "completed"].includes(
    (value as { status?: string }).status ?? ""
  )

/** 校验并提取一份清单；形状不对（比如流式时截断）就当没有。 */
const parseTodos = (value: unknown): TodoItem[] | null => {
  if (!Array.isArray(value)) return null
  const todos = value.filter(isTodoItem)
  return todos.length > 0 ? todos : null
}

/**
 * 从历史消息里倒序找最后一条带 `write_todos` 调用的 AI 消息。
 *
 * 实时值来自 SSE 的 `custom:todos`，但刷新页面后事件流里已经没有上一轮的
 * 记录了——历史恢复不新增 schema，清单本身就在 `write_todos` 的 tool_call
 * args 里（后端落库时会带上），这里把它挖出来当初始值。
 */
const todosFromHistory = (messages: BaseMessage[]): TodoItem[] | null => {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    if (message.type !== "ai") continue
    const calls = (
      message as { tool_calls?: { name?: string; args?: unknown }[] }
    ).tool_calls
    if (!calls) continue
    for (let j = calls.length - 1; j >= 0; j--) {
      const call = calls[j]
      if (call.name !== "write_todos") continue
      const args = call.args as { todos?: unknown } | undefined
      const todos = parseTodos(args?.todos)
      if (todos) return todos
    }
  }
  return null
}

/**
 * Agent 的内部 todo 清单。实时值 + 历史兜底，统一返回渲染需要的派生字段。
 *
 * `useExtension(stream, "todos")` 订阅的是 `custom:todos` 通道并只保留最新一条，
 * 正是为「当前进度」这类面板设计的。模型判断任务简单、不调 `write_todos` 时
 * 这个值一直是 undefined，由 `todos.length === 0` 决定面板不渲染。
 */
export const useTodos = ({
  stream,
  historyMessage,
}: {
  stream: ReturnType<typeof useStreamContext>
  historyMessage: BaseMessage[]
}) => {
  const live = useExtension<TodosPayload>(stream, "todos")

  return useMemo(() => {
    const todos = live?.todos ?? todosFromHistory(historyMessage) ?? []
    const done = todos.filter((todo) => todo.status === "completed").length
    const current = todos.find((todo) => todo.status === "in_progress")
    return {
      todos,
      done,
      total: todos.length,
      current: current?.content,
    }
  }, [live, historyMessage])
}

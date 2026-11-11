"use client"

import { useCallback, useEffect, useMemo, useRef } from "react"

import {
  AIMessage as LangchainAIMessage,
  ToolMessage,
} from "@langchain/core/messages"
import type { BaseMessage } from "@langchain/core/messages"
import type { useStreamContext } from "@langchain/react"
import type { QueryClient } from "@tanstack/react-query"

import { TypeParmas } from "@/app/(home)/_components/composer"
import { getMessageChatMessageIdGetQueryKey } from "@/api/generated/chat/chat"
import type { MessageListResponse } from "@/api/generated/model/messageListResponse"
import { MessageItem } from "@/api/generated/model/messageItem"
import { MessageMode } from "@/api/generated/model/messageMode"
import { toHistoryMessages } from "@/lib/agent-stream/chat-history"

type ChatMessageSources = {
  sessionId: string
  stream: ReturnType<typeof useStreamContext>
  queryClient: QueryClient
  // 生成的重载签名套 ReturnType 会退化成 {}，这里只声明用到的形状。
  historyQuery: {
    data?: MessageListResponse
    isLoading: boolean
    isSuccess: boolean
  }
}

/**
 * 纯派生层：数据源（stream / queryClient / historyQuery）由调用方准备好传入，
 * 这里只负责把两条来源整理成可渲染的列表，并在流结束时回写缓存。
 *
 * 历史来自 `GET /chat/message/{id}`，SSE 只负责「这一轮」的增量：
 * - 事件缓冲每轮开始时清空（后端 ThreadSession.start_run），所以重新进入会话时
 *   回放里只有进行中的这一轮，不会把历史再演一遍；
 * - 仍有极小窗口：本轮已落库但回放还在。这里再按 LangChain 消息 id 去一次重，
 *   落库的 assistant 消息 id 与 SSE 的 message id 是同一个。
 *
 * 两条来源各自成列表，只做「按 id 去重」这一处交集，不合并数组。
 */
export const useChatMessage = ({
  sessionId,
  stream,
  queryClient,
  historyQuery,
}: ChatMessageSources) => {
  const wasLoading = useRef(false)
  const syncedRef = useRef<string | null>(null)
  // stream.messages 在同一 thread 内是跨轮累积的（SDK 只在换 thread 时重置），
  // 回写「本轮」的 parts 时必须先减掉这一轮开始前就存在的消息，否则每轮都会把
  // 前几轮的 id 再写一遍，缓存里同一个消息 id 出现多次，撞 React key。
  const roundBaselineRef = useRef<Set<string>>(new Set())
  // 本轮提交时选的模型 / 模式：流完成时回写 MessageItem 要用，但 stream 的
  // 事件里不带这两项，只能记在提交那一刻。
  const lastPromptRef = useRef<TypeParmas | null>(null)

  // 摊平后按消息 id 去重：缓存里可能同时有「服务端落库行」和「流结束时本地
  // append 的行」，两边的 parts 是同一批 lc_run--* id，不去重会撞 React key。
  const historyMessage = useMemo<BaseMessage[]>(() => {
    const seen = new Set<string>()
    const result: BaseMessage[] = []
    for (const item of historyQuery.data?.data ?? []) {
      for (const message of toHistoryMessages(item)) {
        if (message.id) {
          if (seen.has(message.id)) continue
          seen.add(message.id)
        }
        result.push(message)
      }
    }
    return result
  }, [historyQuery.data])

  const streamLiveMessage = useMemo<BaseMessage[]>(() => {
    return stream.messages.filter((message) => message != null)
  }, [stream.messages])

  // 引用要稳定：下面的回写 effect 依赖它，否则每次渲染都会重跑。
  const appendChatMessage = useCallback(
    (message: MessageItem) => {
      queryClient.setQueryData(
        getMessageChatMessageIdGetQueryKey(sessionId),
        (prev: MessageListResponse | undefined) =>
          prev
            ? {
                ...prev,
                data: [...prev.data, message],
                total: prev.total + 1,
              }
            : prev
      )
    },
    [queryClient, sessionId]
  )

  // 流结束时把这一轮写回历史缓存，刷新后仍能看到。
  useEffect(() => {
    const finished = wasLoading.current && !stream.isLoading
    wasLoading.current = stream.isLoading
    if (!finished) return

    const last = stream.messages.at(-1)
    if (!last || !LangchainAIMessage.isInstance(last) || !last.text) return
    // 同一个 id 只写一次，防止 effect 因其他依赖重跑时重复插入
    const key = last.id ?? last.text
    if (syncedRef.current === key) return
    syncedRef.current = key

    // parts 要的是后端 message_to_dict() 的形状（{ type: "ai", data: {...} }），
    // 和 toHistoryMessages 反解析的是同一套；直接塞 BaseMessage 实例会被它
    // 的 `isRecord(part.data)` 判空跳过，刷新后消息就没了。
    const roundMessages = streamLiveMessage.filter(
      (message) => !message.id || !roundBaselineRef.current.has(message.id)
    )
    const lastPrompt = lastPromptRef.current
    appendChatMessage({
      id: last.id ?? crypto.randomUUID(),
      role: "assistant",
      status: "complete",
      model: lastPrompt?.model ?? "",
      mode: lastPrompt?.mode ?? MessageMode.agent,
      parts: roundMessages
        // 工具结果也要写进去，否则刷新后展开 tool_call 是空的。
        .filter(
          (message) =>
            LangchainAIMessage.isInstance(message) ||
            ToolMessage.isInstance(message)
        )
        // StoredMessage 是 interface，没有索引签名，直接赋给
        // `{ [key: string]: unknown }[]` 那一支过不了 TS；运行时形状就是普通对象。
        .map(
          (message) => message.toDict() as unknown as Record<string, unknown>
        ),
      created_at: new Date().toISOString(),
    })
  }, [stream.isLoading, stream.messages, streamLiveMessage, appendChatMessage])

  const submit = (prompt: TypeParmas) => {
    if (stream.isLoading) return false

    // 新一轮开始：完成回写用的是这一轮的 model / mode，上一轮的不能留。
    lastPromptRef.current = prompt
    syncedRef.current = null
    // 记下当前已存在的消息 id，回写时据此只取本轮新增的部分。
    roundBaselineRef.current = new Set(
      stream.messages.flatMap((message) => (message.id ? [message.id] : []))
    )
    void stream.submit({ ...prompt })

    // 后端不把 user 消息回显进 SSE，历史又只在进入会话时拉一次，
    // 所以先在缓存里补一条，等下一轮刷新时再被服务端的同内容消息替换掉。
    const userMessage: MessageItem = {
      id: crypto.randomUUID(),
      role: "user",
      status: "complete",
      model: prompt.model!,
      mode: prompt.mode!,
      parts: prompt.parts,
      created_at: new Date().toISOString(),
    }
    appendChatMessage(userMessage)
    return true
  }

  return {
    historyMessage,
    streamLiveMessage,
    isLoading: stream.isLoading,
    // 首次拉历史才有 loading；后台 refetch 时 isLoading 为 false，不应该让列表闪骨架。
    isHistoryLoading: historyQuery.isLoading,
    // 由 false 变 true 的那一刻就是「历史到手」，用它触发一次置底；
    // 换用 historyMessage.length 会在上一轮回写缓存时重复触发。
    isHistoryLoaded: historyQuery.isSuccess,
    error: stream.error,
    submit,
  }
}

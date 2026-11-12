"use client"

import { useEffect, useState } from "react"

import { useStreamContext } from "@langchain/react"
import { useQueryClient } from "@tanstack/react-query"

import { Composer, TypeParmas } from "@/app/(home)/_components/composer"
import { useThreadAbortAgentsSessionIdAbortPost } from "@/api/generated/agent/agent"
import { useMessageChatMessageIdGet } from "@/api/generated/chat/chat"

import { useChatMessage } from "../hook/use-chat-message"
import { useScrollToBottom } from "../hook/use-scroll-to-bottom"
import { LoadingIndicator } from "./loading-indicator"
import { MessageList } from "./message-list"
import LeftHeader from "./left-header"

/**
 * 必须在 StreamProvider 内部：useStreamContext 从 context 读，
 * 挂在 Provider 外面拿不到。数据源在这里取，派生交给 useChatMessage。
 */
function ChatPanel({ sessionId }: { sessionId: string }) {
  const stream = useStreamContext()
  const queryClient = useQueryClient()
  const historyQuery = useMessageChatMessageIdGet(sessionId)
  const abortMutation = useThreadAbortAgentsSessionIdAbortPost()

  const {
    historyMessage,
    streamLiveMessage,
    isLoading,
    isHistoryLoading,
    isHistoryLoaded,
    error,
    submit,
  } = useChatMessage({ sessionId, stream, queryClient, historyQuery })
  const [promptValue, setPromptValue] = useState("")
  const { scrollRef, contentRef, handleScroll, scrollToBottom } =
    useScrollToBottom()

  // 历史到手后无条件置底：重新进入会话时用户处在任何位置，都应该看到最新一条。
  useEffect(() => {
    if (!isHistoryLoaded) return
    scrollToBottom()
  }, [isHistoryLoaded, scrollToBottom])

  // 提交后无条件置底。用「isLoading 变 true」而不是「内容变长」，因为用户可能
  // 已经往上翻了，这种情况下内容变化本身不再触发滚动，但提交必须把他拉回来。
  useEffect(() => {
    if (!isLoading) return
    scrollToBottom()
  }, [isLoading, scrollToBottom])

  const handleSubmit = (prompt: TypeParmas) => {
    if (!submit(prompt)) return
    setPromptValue("")
  }

  // 中止由后端执行：run 停下来后还会补一条终止 lifecycle，
  // 前端据此把 isLoading 收回去，所以这里不额外断开 SSE。
  const handleAbort = () => {
    abortMutation.mutate({ sessionId })
  }

  const isEmpty = historyMessage.length === 0 && streamLiveMessage.length === 0

  return (
    <div
      style={{ width: "440px" }}
      className="flex min-h-0 flex-1 flex-col pr-2 pl-3"
    >
      <LeftHeader />
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="scroll-bar flex-1 overflow-y-auto"
      >
        <div ref={contentRef} className="pr-0,5 pb-4 pl-1.5">
          {isEmpty && !isHistoryLoading ? (
            <div className="text-sm text-muted-foreground">
              发一条消息开始对话
            </div>
          ) : null}

          {!isLoading && isHistoryLoading ? (
            <LoadingIndicator label="加载中" className="justify-center" />
          ) : null}

          <MessageList messages={historyMessage} sessionId={sessionId} />

          {isLoading ? (
            <MessageList
              messages={streamLiveMessage}
              sessionId={sessionId}
              streaming
            />
          ) : null}

          {isLoading ? <LoadingIndicator label="思考中" /> : null}
          {error ? (
            <div className="text-sm text-destructive">
              {error instanceof Error
                ? error.message
                : typeof error === "string"
                  ? error
                  : "请求失败，请稍后重试。"}
            </div>
          ) : null}
        </div>
      </div>

      <Composer
        className="my-2 shrink-0"
        loading={isLoading}
        prompt={promptValue}
        onPromptChange={setPromptValue}
        onSubmit={handleSubmit}
        onAbort={handleAbort}
      />
    </div>
  )
}

export default ChatPanel

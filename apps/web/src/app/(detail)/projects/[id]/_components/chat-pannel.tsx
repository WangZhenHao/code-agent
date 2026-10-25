"use client";

import { useEffect, useState } from "react";

import { useStreamContext } from "@langchain/react";
import { useQueryClient } from "@tanstack/react-query";

import { Composer, TypeParmas } from "@/app/(home)/_components/composer";
import { useMessageChatMessageIdGet } from "@/api/generated/chat/chat";

import { useChatMessage } from "./hook/use-chat-message";
import { useScrollToBottom } from "./hook/use-scroll-to-bottom";
import { AIMessage } from "./message";

/**
 * 必须在 StreamProvider 内部：useStreamContext 从 context 读，
 * 挂在 Provider 外面拿不到。数据源在这里取，派生交给 useChatMessage。
 */
function ChatPanel({ sessionId }: { sessionId: string }) {
  const stream = useStreamContext();
  const queryClient = useQueryClient();
  const historyQuery = useMessageChatMessageIdGet(sessionId);

  const {
    historyMessage,
    streamLiveMessage,
    isLoading,
    isHistoryLoading,
    isHistoryLoaded,
    error,
    submit,
  } = useChatMessage({ sessionId, stream, queryClient, historyQuery });
  const [promptValue, setPromptValue] = useState("");
  const { scrollRef, contentRef, handleScroll, scrollToBottom } =
    useScrollToBottom();

  // 历史到手后无条件置底：重新进入会话时用户处在任何位置，都应该看到最新一条。
  useEffect(() => {
    if (!isHistoryLoaded) return;
    scrollToBottom();
  }, [isHistoryLoaded, scrollToBottom]);

  // 提交后无条件置底。用「isLoading 变 true」而不是「内容变长」，因为用户可能
  // 已经往上翻了，这种情况下内容变化本身不再触发滚动，但提交必须把他拉回来。
  useEffect(() => {
    if (!isLoading) return;
    scrollToBottom();
  }, [isLoading, scrollToBottom]);

  const handleSubmit = (prompt: TypeParmas) => {
    if (!submit(prompt)) return;
    setPromptValue("");
  };

  const isEmpty = historyMessage.length === 0 && streamLiveMessage.length === 0;

  return (
    <div
      style={{ width: "440px" }}
      className="border-r pl-3 pr-2 flex flex-col h-full"
    >
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto space-y-3 py-4 scroll-bar"
      >
        <div ref={contentRef} className="pr-0,5 pl-1.5">
          {isEmpty && !isHistoryLoading ? (
            <div className="text-sm text-muted-foreground">
              发一条消息开始对话
            </div>
          ) : null}

          {isHistoryLoading ? (
            <div className="text-sm text-muted-foreground">加载中…</div>
          ) : null}

          {historyMessage.map((message, index) => (
            <AIMessage key={message.id ?? `history-${index}`} message={message} />
          ))}

          {isLoading &&
            streamLiveMessage.map((message, index) => (
              <AIMessage key={message.id ?? `live-${index}`} message={message} />
            ))}

          {isLoading ? (
            <div className="text-sm text-muted-foreground">思考中…</div>
          ) : null}

          {error ? (
            <div className="text-sm text-destructive">
              {error instanceof Error ? error.message : String(error)}
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
      />
    </div>
  );
}

export default ChatPanel;

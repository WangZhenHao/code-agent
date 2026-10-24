"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, ReactNode } from "react";

import type { BaseMessage } from "@langchain/core/messages";
import {
  StreamProvider as StreamProviderBase,
  useStreamContext,
} from "@langchain/react";
import { useQueryClient } from "@tanstack/react-query";

import { Composer, TypeParmas } from "@/app/(home)/_components/composer";
import {
  getMessageChatMessageIdGetQueryKey,
  useMessageChatMessageIdGet,
} from "@/api/generated/chat/chat";
import { createAgentTransport } from "@/lib/agent-stream/agent-stream";
import { toHistoryMessages } from "@/lib/agent-stream/chat-history";

import { AIMessage } from "./message";

/**
 * @langchain/react 1.2 的 StreamProvider 声明返回 ReactNode，而 @types/react
 * 19.3 的 JSX 校验要求组件返回 Element | null，直接当组件用会报 TS2786。
 * 运行时它就是个普通函数组件（内部 return 一个 provider 元素），这里只修类型。
 */
const StreamProvider = StreamProviderBase as unknown as ComponentType<{
  threadId: string;
  transport: ReturnType<typeof createAgentTransport>;
  optimistic?: boolean;
  children: ReactNode;
}>;

const Left = ({ sessionId }: { sessionId: string }) => {
  // 会话变了就重建 adapter，并靠 key 让 StreamProvider 整棵子树重挂，
  // 否则上一个会话的流状态会留在 context 里。
  const transport = useMemo(() => createAgentTransport(sessionId), [sessionId]);

  return (
    // optimistic 关掉：后端不把 user 消息回显进 messages 通道，开着的话乐观插入的
    // 那条会一直停在 pending，且没有 state 接口可供 reconcile。
    <StreamProvider
      key={sessionId}
      threadId={sessionId}
      transport={transport}
      optimistic={false}
    >
      <ChatPanel sessionId={sessionId} />
    </StreamProvider>
  );
};

/**
 * 必须在 StreamProvider 内部：useStreamContext 从 context 读，
 * 挂在 Provider 外面拿不到。
 *
 * 历史来自 `GET /chat/message/{id}`，SSE 只负责「这一轮」的增量：
 * - 事件缓冲每轮开始时清空（后端 ThreadSession.start_run），所以重新进入会话时
 *   回放里只有进行中的这一轮，不会把历史再演一遍；
 * - 仍有极小窗口：本轮已落库但回放还在。这里再按 LangChain 消息 id 去一次重，
 *   落库的 assistant 消息 id 与 SSE 的 message id 是同一个。
 *
 * 两条来源各自成列表，只做「按 id 去重」这一处交集，不合并数组。
 */
function ChatPanel({ sessionId }: { sessionId: string }) {
  const stream = useStreamContext();
  const queryClient = useQueryClient();
  const [promptValue, setPromptValue] = useState("");

  const historyQuery = useMessageChatMessageIdGet(sessionId);
  const history = useMemo<BaseMessage[]>(
    () =>
      (historyQuery.data?.data ?? []).flatMap((item) =>
        toHistoryMessages(item)
      ),
    [historyQuery.data]
  );

  // 一轮跑完后刷新历史：下一次进入会话就不依赖事件回放。
  const wasLoading = useRef(stream.isLoading);
  useEffect(() => {
    if (wasLoading.current && !stream.isLoading) {
      void queryClient.invalidateQueries({
        queryKey: getMessageChatMessageIdGetQueryKey(sessionId),
      });
    }
    wasLoading.current = stream.isLoading;
  }, [stream.isLoading, queryClient, sessionId]);

  const live = useMemo<BaseMessage[]>(() => {
    const persisted = new Set(
      history.flatMap((message) => (message.id ? [message.id] : []))
    );
    return stream.messages
      .filter((message) => message != null && message.type !== "human")
      .filter((message) => !(message.id && persisted.has(message.id)));
  }, [history, stream.messages]);

  const handleSubmit = (prompt: TypeParmas) => {
    if (stream.isLoading) return;

    // Composer 给的已经接近 ChatCreateRequest 的形状（mode/model/parts）。
    // 展开成普通对象再传：SDK 的 submit 入参是带索引签名的记录，
    // 直接传 interface 过不了类型；onRequest 会把它当作 params.input，
    // 由 toCommandBody 取 parts/mode/model 交给后端的 `req`。
    setPromptValue("");
    void stream.submit({ ...prompt });
  };

  return (
    <div
      style={{ width: "440px" }}
      className="border-r pl-3 pr-2 flex flex-col h-full"
    >
      <div className="flex-1 overflow-y-auto space-y-3 py-4 scroll-bar">
        <div className="pr-0,5 pl-1.5">
          {history.length === 0 && live.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              发一条消息开始对话
            </div>
          ) : null}

          {history.map((message, index) => (
            <AIMessage
              key={message.id ?? `history-${index}`}
              message={message}
            />
          ))}

          {live.map((message, index) => (
            <AIMessage key={message.id ?? `live-${index}`} message={message} />
          ))}

          {stream.isLoading ? (
            <div className="text-sm text-muted-foreground">思考中…</div>
          ) : null}

          {stream.error ? (
            <div className="text-sm text-destructive">
              {stream.error instanceof Error
                ? stream.error.message
                : String(stream.error)}
            </div>
          ) : null}
        </div>
      </div>

      <Composer
        className="my-2 shrink-0"
        loading={stream.isLoading}
        prompt={promptValue}
        onPromptChange={setPromptValue}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default Left;

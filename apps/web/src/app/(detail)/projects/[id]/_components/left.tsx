"use client";

import { useMemo } from "react";
import type { ComponentType, ReactNode } from "react";

import { useParams } from "next/navigation";

import { StreamProvider as StreamProviderBase } from "@langchain/react";

import { createAgentTransport } from "@/lib/agent-stream/agent-stream";

import ChatPanel from "./left/chat-pannel";

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

const Left = () => {
  // 路由 /projects/[id] 的 id 就是后端的 session_id，也是 LangGraph 的 thread id
  const { id: sessionId } = useParams<{ id: string }>();

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
      <div className="flex h-full flex-col">
        <ChatPanel sessionId={sessionId} />
      </div>
    </StreamProvider>
  );
};

export default Left;

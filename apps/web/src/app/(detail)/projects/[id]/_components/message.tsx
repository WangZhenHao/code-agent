"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import Markdown from "@/components/custom/markdown";
import { AIMessage as LangchainAIMessage } from "@langchain/core/messages";
import type { BaseMessage } from "@langchain/core/messages";

/**
 * 一条消息的统一渲染：历史的（REST）和实时的（SSE）都是 `BaseMessage`，
 * 所以这个组件不关心来源，只按类型分支。
 *
 * tool 结果不进气泡（后端也不把它当一轮的展示内容），返回 null 即可。
 */

const User = ({ message }: { message: BaseMessage }) => {
  return (
    <div className="text-sm mt-4">
      <div className="flex justify-end items-center mb-1 text-muted-foreground">
        <Avatar className="size-8">
          <AvatarImage alt="头像" />
          <AvatarFallback>U</AvatarFallback>
        </Avatar>
        <span className="ml-1 text-xs">用户</span>
      </div>
      <div className="flex justify-end mt-3">
        <div className=" px-2.5 py-2 rounded-md bg-input">{message.text}</div>
      </div>
    </div>
  );
};
const System = ({ message }: { message: BaseMessage }) => {
  const toolCalls = LangchainAIMessage.isInstance(message)
    ? (message.tool_calls ?? []).flatMap((call) =>
        call.name ? [call.name] : []
      )
    : [];

  return (
    <div className="mt-4">
      {toolCalls.length > 0 ? (
        <ul className="mb-1 space-y-1 text-xs text-muted-foreground">
          {toolCalls.map((name, index) => (
            <li key={`${message.id ?? "tool"}-${index}`}>
              <strong>{name}</strong>
            </li>
          ))}
        </ul>
      ) : null}
      {message.text ? <Markdown text={message.text} /> : null}
    </div>
  );
};
export const AIMessage = ({ message }: { message: BaseMessage }) => {
  const isUser = message.type === "human";
  if (!isUser && message.type !== "ai") return null;

  return isUser ? <User message={message} /> : <System message={message} />;
};

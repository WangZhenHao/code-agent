"use client"

import Markdown from "@/components/custom/markdown"
import {
  AIMessage as LangchainAIMessage,
  type BaseMessage,
  type ToolMessage,
} from "@langchain/core/messages"

import { ToolCall } from "./tool-call"

/**
 * 助手消息：工具调用列表在上，正文 Markdown 在下。
 *
 * `toolResults` 由 MessageList 按 tool_call_id 配好传进来——tool_calls 本身
 * 只有参数，输出在另一条 ToolMessage 里。
 */
export const System = ({
  message,
  toolResults,
}: {
  message: BaseMessage
  toolResults: Map<string, ToolMessage>
}) => {
  const toolCalls = LangchainAIMessage.isInstance(message)
    ? (message.tool_calls ?? [])
    : []

  return (
    <div className="mt-4">
      {toolCalls.length > 0 ? (
        <ul className="mb-1 space-y-1 text-xs text-muted-foreground">
          {toolCalls.map((call, index) => (
            <ToolCall
              key={call.id ?? `${message.id ?? "tool"}-${index}`}
              name={call.name ?? "tool"}
              args={call.args}
              result={call.id ? toolResults.get(call.id) : undefined}
            />
          ))}
        </ul>
      ) : null}
      {message.text ? <Markdown text={message.text} /> : null}
    </div>
  )
}

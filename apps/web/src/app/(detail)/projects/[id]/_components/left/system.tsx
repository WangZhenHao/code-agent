"use client"

import Markdown from "@/components/custom/markdown"
import {
  AIMessage as LangchainAIMessage,
  type BaseMessage,
  type ToolMessage,
} from "@langchain/core/messages"

import { Reasoning } from "./reasoning"
import { ToolCall } from "./tool-call"

/**
 * 助手消息：思考过程在上，工具调用居中，正文 Markdown 在下。
 *
 * `toolResults` 由 MessageList 按 tool_call_id 配好传进来——tool_calls 本身
 * 只有参数，输出在另一条 ToolMessage 里。
 *
 * 思考过程来自 `contentBlocks` 的 reasoning 块：`message.text` 只拼 text 块，
 * 直接用它会把 reasoning 丢掉。历史和 SSE 都是 `output_version: "v1"` 的形状。
 */
export const System = ({
  message,
  toolResults,
  streaming = false,
}: {
  message: BaseMessage
  toolResults: Map<string, ToolMessage>
  streaming?: boolean
}) => {
  // `write_todos` 是 Agent 内部的任务清单工具，真正的进度由上面的 todo 面板
  // 展示；混进下面这排真实工具调用里只会让用户以为它又是一个普通操作。
  const toolCalls = LangchainAIMessage.isInstance(message)
    ? (message.tool_calls ?? []).filter((call) => call.name !== "write_todos")
    : []
  const reasoning = LangchainAIMessage.isInstance(message)
    ? message.contentBlocks
        .flatMap((block) =>
          block.type === "reasoning" ? [block.reasoning] : []
        )
        .join("\n\n")
    : ""

  return (
    <div className="mt-4">
      <Reasoning text={reasoning} streaming={streaming} />
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

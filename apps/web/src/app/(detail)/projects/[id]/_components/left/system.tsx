"use client"

import Markdown from "@/components/custom/markdown"
import {
  AIMessage as LangchainAIMessage,
  type BaseMessage,
} from "@langchain/core/messages"

import { Reasoning } from "./reasoning"
import { ToolCall } from "./tool-call"

/**
 * 助手消息：思考过程在上，工具调用居中，正文 Markdown 在下。
 *
 * 工具结果不在这里配对了：输出改由 ToolCall 内部按 `tool_call_id` 查接口
 * （`GET /agents/{id}/tools/{tool_call_id}`），SSE 和历史里都不再带工具正文。
 *
 * 思考过程来自 `contentBlocks` 的 reasoning 块：`message.text` 只拼 text 块，
 * 直接用它会把 reasoning 丢掉。历史和 SSE 都是 `output_version: "v1"` 的形状。
 */
export const System = ({
  message,
  sessionId,
  streaming = false,
}: {
  message: BaseMessage
  sessionId: string
  streaming?: boolean
}) => {
  const toolCalls = LangchainAIMessage.isInstance(message)
    ? (message.tool_calls ?? [])
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
              sessionId={sessionId}
              toolCallId={call.id}
              name={call.name ?? "tool"}
              args={call.args}
            />
          ))}
        </ul>
      ) : null}
      {message.text ? <Markdown text={message.text} /> : null}
    </div>
  )
}

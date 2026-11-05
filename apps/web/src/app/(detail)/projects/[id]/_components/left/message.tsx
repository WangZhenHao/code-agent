"use client"

import { Fragment, useMemo } from "react"

import { ToolMessage, type BaseMessage } from "@langchain/core/messages"

import { System } from "./system"
import { User } from "./user"

/**
 * 消息列表的统一渲染：历史的（REST）和实时的（SSE）都是 `BaseMessage[]`，
 * 所以这里不关心来源，只按类型分支。
 *
 * tool 结果不单独成气泡：它按 tool_call_id 挂在对应工具调用下面，
 * 点一下展开 / 收起（见 ./tool-call）。配对在同一次渲染里完成，
 * 调用方只管把消息数组给进来。
 */

const renderMessage = (
  message: BaseMessage,
  toolResults: Map<string, ToolMessage>
) => {
  if (message.type === "human") return <User message={message} />
  if (message.type !== "ai") return null
  return <System message={message} toolResults={toolResults} />
}

export const MessageList = ({ messages }: { messages: BaseMessage[] }) => {
  // 工具结果按 tool_call_id 索引：tool_calls 只带参数，输出来自另一条 ToolMessage。
  // 历史和 SSE 的列表形状一致，都走这里。
  const toolResults = useMemo(() => {
    const map = new Map<string, ToolMessage>()
    for (const message of messages) {
      if (ToolMessage.isInstance(message))
        map.set(message.tool_call_id, message)
    }
    return map
  }, [messages])

  return (
    <>
      {messages.map((message, index) => (
        <Fragment key={message.id ?? `message-${index}`}>
          {renderMessage(message, toolResults)}
        </Fragment>
      ))}
    </>
  )
}

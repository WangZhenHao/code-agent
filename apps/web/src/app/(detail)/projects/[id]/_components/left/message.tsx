"use client"

import { Fragment } from "react"

import type { BaseMessage } from "@langchain/core/messages"

import { System } from "./system"
import { User } from "./user"

/**
 * 消息列表的统一渲染：历史的（REST）和实时的（SSE）都是 `BaseMessage[]`，
 * 所以这里不关心来源，只按类型分支。
 *
 * tool 结果不单独成气泡：它按 tool_call_id 挂在对应工具调用下面，
 * 点一下展开 / 收起（见 ./tool-call）。结果的获取在 ToolCall 内部按 id 查接口，
 * 这里只负责把 sessionId 传下去。
 */

const renderMessage = (
  message: BaseMessage,
  sessionId: string,
  streaming: boolean
) => {
  if (message.type === "human") return <User message={message} />
  if (message.type !== "ai") return null
  return (
    <System message={message} sessionId={sessionId} streaming={streaming} />
  )
}

export const MessageList = ({
  messages,
  sessionId,
  streaming = false,
}: {
  messages: BaseMessage[]
  sessionId: string
  /** 这份列表是否还在流式输出：只有最后一条算「进行中」，思考过程据此展开。 */
  streaming?: boolean
}) => {
  return (
    <>
      {messages.map((message, index) => (
        <Fragment key={message.id ?? `message-${index}`}>
          {renderMessage(
            message,
            sessionId,
            streaming && index === messages.length - 1
          )}
        </Fragment>
      ))}
    </>
  )
}

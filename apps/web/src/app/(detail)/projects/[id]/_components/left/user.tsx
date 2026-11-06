"use client"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import type { BaseMessage } from "@langchain/core/messages"

/** 用户消息：右侧头像 + 灰底气泡，内容原样输出，不解析 Markdown。 */
export const User = ({ message }: { message: BaseMessage }) => {
  return (
    <div className="mt-4 text-sm">
      <div className="mb-1 flex items-center justify-end text-muted-foreground">
        <Avatar className="size-8">
          <AvatarImage alt="头像" />
          <AvatarFallback>U</AvatarFallback>
        </Avatar>
        <span className="ml-1 text-xs">用户</span>
      </div>
      <div className="mt-3 flex justify-end">
        <div className="max-h-80 max-w-[96%] min-w-0 overflow-y-auto rounded-md bg-input px-2.5 py-2 whitespace-pre-wrap wrap-break-word">
          {message.text}
        </div>
      </div>
    </div>
  )
}

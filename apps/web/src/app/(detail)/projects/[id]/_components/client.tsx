"use client"

import "./client.css"

import { useParams } from "next/navigation"

import { WsProvider } from "@/components/providers/ws-provider"

import Left from "./left"
import Right from "./right"
import { useDetailChatDetailIdGet } from "@/api/generated/chat/chat"

const Client = () => {
  // 路由 /projects/[id] 的 id 就是后端 session_id（devbox_id）。
  // key 保证切会话时重建连接——一个 session 只能有一条 ws。
  const { id: sessionId } = useParams<{ id: string }>()
  const detailInfo = useDetailChatDetailIdGet(sessionId)

  return (
    <WsProvider key={sessionId} devboxId={sessionId}>
      <div className="flex h-screen bg-sidebar">
        <Left />
        <Right />
      </div>
    </WsProvider>
  )
}

export default Client

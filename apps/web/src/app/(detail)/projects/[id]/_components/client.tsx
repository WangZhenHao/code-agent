"use client"

import "./client.css"

import { useParams } from "next/navigation"

import { WsProvider } from "@/components/providers/ws-provider"

import Left from "./left"
import Right from "./right"
import { useDetailChatDetailIdGet } from "@/api/generated/chat/chat"
import { useProjectDetailStore } from "@/store/project-detail"
import React from "react"

const Client = () => {
  // 路由 /projects/[id] 的 id 就是后端 session_id（devbox_id）。
  // key 保证切会话时重建连接——一个 session 只能有一条 ws。
  const { id: sessionId } = useParams<{ id: string }>()
  const detailInfoData = useDetailChatDetailIdGet(sessionId)
  const setInfo = useProjectDetailStore((state) => state.setInfo)

  // 将获取到的详情数据设置到全局状态中
  React.useEffect(() => {
    if (detailInfoData.data) {
      setInfo(detailInfoData.data)
    }
  }, [detailInfoData.data, setInfo])

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

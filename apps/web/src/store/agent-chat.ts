"use client"

import { useSyncExternalStore } from "react"
import { create } from "zustand"
import { persist } from "zustand/middleware"

import type { MessageMode } from "@/api/generated/model"
import { DEFAULT_MODEL, DEFAULT_MODE } from "@/lib/chat-options"

interface AgentChatState {
  /** 对话模式：agent 或 plan */
  mode: MessageMode
  /** 传给后端 ChatCreateRequest.model 的模型标识 */
  model: string
  prompt: string
  setMode: (mode: MessageMode) => void
  setModel: (model: string) => void
  setPrompt: (prompt: string) => void
}

/**
 * 发起对话前用户选择的全局配置。
 *
 * 首页 Composer、后续详情页的重试/续聊按钮都从这里读取，保证一次会话用的是
 * 同一套 mode/model。选择会持久化到 localStorage，刷新后沿用上次的选择。
 */
export const useAgentChatStore = create<AgentChatState>()(
  persist(
    (set) => ({
      mode: DEFAULT_MODE,
      model: DEFAULT_MODEL,
      prompt: "",
      setMode: (mode) => set({ mode }),
      setModel: (model) => set({ model }),
      setPrompt: (prompt) => set({ prompt }),
    }),
    {
      name: "code-agent-agent-chat",
      partialize: (state) => ({
        mode: state.mode,
        model: state.model,
        prompt: state.prompt,
      }),
    }
  )
)

/** persist 在客户端挂载后才完成回填，用该标记避免 SSR / 首屏渲染不一致 */
export function useAgentChatHydrated() {
  return useSyncExternalStore(
    (onChange) => {
      const persist = useAgentChatStore.persist
      if (!persist) return useAgentChatStore.subscribe(onChange)
      const unsubscribeHydration = persist.onFinishHydration(onChange)
      const unsubscribeStore = useAgentChatStore.subscribe(onChange)
      return () => {
        unsubscribeHydration()
        unsubscribeStore()
      }
    },
    () => useAgentChatStore.persist?.hasHydrated() ?? false,
    () => false
  )
}

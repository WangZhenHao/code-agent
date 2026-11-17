"use client"

import { useSyncExternalStore } from "react"
import { create } from "zustand"
import { persist } from "zustand/middleware"
import { AppWindow, FileCode } from "lucide-react"

import type { TabItem } from "@/app/(detail)/projects/[id]/_components/right/header"

interface Operation {
  /** 当前选中的 tab：固定 tab 用 "preview"，文件 tab 用 file 的 value */
  currentTab: string
  /** 追加在「预览」之后的可关闭 tab，按打开顺序排列 */
  tabList: TabItem[]

  showCodeFileTree: boolean
}

interface ProjectOperateState {
  operation: Operation

  /** 批量更新 operation 的字段（浅 merge） */
  updateField: (patch: Partial<Operation>) => void

  /** 切换文件树显隐 */
  toggleCodeFileTree: () => void
}

/** 固定 tab：预览永远排第一个，不参与关闭 */
export const PREVIEW_TAB: TabItem = {
  value: "preview",
  label: "预览",
  icon: AppWindow,
}

/** 演示数据：文件树接上接口后删掉 */
const DEMO_TAB: TabItem = {
  value: "codeEditor",
  label: "app/config.ts",
  icon: FileCode,
}

const INITIAL_OPERATION: Operation = {
  currentTab: "preview",
  tabList: [DEMO_TAB],
  showCodeFileTree: false,
}

/**
 * 项目详情页的操作态（当前 tab + 已打开的文件）。
 * 持久化到 localStorage，刷新后沿用上次的 tab 和打开的文件。
 */
export const useProjectOperateStore = create<ProjectOperateState>()(
  persist(
    (set) => ({
      operation: INITIAL_OPERATION,
      updateField: (patch) =>
        set((state) => ({
          operation: { ...state.operation, ...patch },
        })),
      toggleCodeFileTree: () =>
        set((state) => ({
          operation: {
            ...state.operation,
            showCodeFileTree: !state.operation.showCodeFileTree,
          },
        })),
    }),
    {
      name: "code-agent-project-operate",
      // icon 是 React 组件，存不进 localStorage；只存 value/label
      partialize: (state) => ({
        operation: {
          currentTab: state.operation.currentTab,
          showCodeFileTree: state.operation.showCodeFileTree,
          tabList: state.operation.tabList.map(({ value, label }) => ({
            value,
            label,
          })),
        },
      }),
    }
  )
)

/** persist 在客户端挂载后才完成回填，用该标记避免 SSR / 首屏渲染不一致 */
export function useProjectOperateHydrated() {
  return useSyncExternalStore(
    (onChange) => {
      // 服务端（SSR）拿不到 persist API，回退到普通 store 订阅
      const persist = useProjectOperateStore.persist
      if (!persist) return useProjectOperateStore.subscribe(onChange)
      const unsubscribeHydration = persist.onFinishHydration(onChange)
      const unsubscribeStore = useProjectOperateStore.subscribe(onChange)
      return () => {
        unsubscribeHydration()
        unsubscribeStore()
      }
    },
    () => useProjectOperateStore.persist?.hasHydrated() ?? false,
    () => false
  )
}

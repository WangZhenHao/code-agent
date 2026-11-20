"use client"

import { useSyncExternalStore } from "react"
import { create } from "zustand"
import { persist } from "zustand/middleware"

import type { TabItem } from "@/app/(detail)/projects/[id]/_components/right/header"

/** 文件 tab 的 value 前缀：`codeEditor:<相对路径>`，路径本身也能从 value 里还原 */
export const CODE_EDITOR_PREFIX = "codeEditor:"

/** 判断某个 tab 是不是文件 tab */
export const isCodeEditorTab = (value: string) =>
  value.startsWith(CODE_EDITOR_PREFIX)

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

  /** 打开（或聚焦）一个文件 tab：已打开则复用，不重复追加 */
  openFile: (path: string, content: string) => void
}

/** 固定 tab：预览永远排第一个，不参与关闭 */
export const PREVIEW_TAB: TabItem = {
  value: "preview",
  label: "预览",
  icon: "preview",
}

const INITIAL_OPERATION: Operation = {
  currentTab: "preview",
  tabList: [],
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
      openFile: (path, content) =>
        set((state) => {
          const value = `${CODE_EDITOR_PREFIX}${path}`
          const exists = state.operation.tabList.some(
            (tab) => tab.value === value
          )
          return {
            operation: {
              ...state.operation,
              currentTab: value,
              tabList: exists
                ? // 已打开过：用最新内容覆盖，避免展示上次的旧内容
                  state.operation.tabList.map((tab) =>
                    tab.value === value ? { ...tab, content } : tab
                  )
                : [
                    ...state.operation.tabList,
                    { value, label: path, content, icon: "path" },
                  ],
            },
          }
        }),
    }),
    {
      name: "code-agent-project-operate",
      // icon 现在是字符串，可以和 content 一起存进 localStorage
      partialize: (state) => ({
        operation: {
          currentTab: state.operation.currentTab,
          showCodeFileTree: state.operation.showCodeFileTree,
          tabList: state.operation.tabList.map(
            ({ value, label, icon, content }) => ({
              value,
              label,
              icon,
              content,
            })
          ),
        },
      }),
      // v0 存的是带 React 组件图标的演示 tab（value 还是无前缀的 "codeEditor"），
      // 形状对不上，直接丢弃重来，避免刷新后渲染出空 tab。
      version: 1,
      migrate: () => ({ operation: INITIAL_OPERATION }),
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

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

  /**
   * 关闭一个 tab（按 value 删除）。关掉的是当前 tab 时退回「预览」；
   * 固定 tab（预览）不受影响，调了也删不掉。
   */
  closeFile: (value: string) => void
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
                    {
                      value,
                      label: path,
                      content,
                      icon: "path",
                      canClose: true,
                    },
                  ],
            },
          }
        }),
      closeFile: (value) =>
        set((state) => {
          // 删的正好是当前 tab：落到「预览」上。文件 tab 以外的项（预览）
          // 本就不在 tabList 里，过滤是空操作。
          const currentTab =
            state.operation.currentTab === value
              ? PREVIEW_TAB.value
              : state.operation.currentTab
          return {
            operation: {
              ...state.operation,
              currentTab,
              tabList: state.operation.tabList.filter(
                (tab) => tab.value !== value
              ),
            },
          }
        }),
    }),
    {
      name: "code-agent-project-operate",
      // icon 现在是字符串，可以和 content 一起存进 localStorage。
      // canClose 必须一起存：丢了它，刷新后文件 tab 就没有关闭图标了。
      partialize: (state) => ({
        operation: {
          currentTab: state.operation.currentTab,
          showCodeFileTree: state.operation.showCodeFileTree,
          tabList: state.operation.tabList.map(
            ({ value, label, icon, content, canClose }) => ({
              value,
              label,
              icon,
              content,
              canClose,
            })
          ),
        },
      }),
      // v0 存的是带 React 组件图标的演示 tab（value 还是无前缀的 "codeEditor"），
      // 形状对不上，直接丢弃重来，避免刷新后渲染出空 tab。
      // v1.1 的 tabList 没存 canClose，补成 true——那时 tabList 里本来就只有文件 tab。
      version: 1.2,
      migrate: (persisted, version) => {
        if (version < 1.1) return { operation: INITIAL_OPERATION }
        // zustand 把 persisted 标成 unknown（真正的形状由 partialize 决定）
        const { operation } = persisted as { operation: Operation }
        return {
          operation: {
            ...operation,
            tabList: operation.tabList.map((tab) => ({
              ...tab,
              canClose: true,
            })),
          },
        }
      },
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

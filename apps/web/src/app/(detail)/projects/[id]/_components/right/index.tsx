"use client"

import { useMemo } from "react"
import { useShallow } from "zustand/react/shallow"

import Header, { type TabItem } from "./header"
import Preview from "./preview"
import CodeEditor from "./code-editor"
import Filetree from "./file-tree"
import {
  PREVIEW_TAB,
  isCodeEditorTab,
  useProjectOperateHydrated,
  useProjectOperateStore,
} from "@/store/project-operate"

const Right = () => {
  const isHydrated = useProjectOperateHydrated()
  const { currentTab, tabList, showCodeFileTree, updateField, closeFile } =
    useProjectOperateStore(
      useShallow((state) => ({
        currentTab: state.operation.currentTab,
        tabList: state.operation.tabList,
        showCodeFileTree: state.operation.showCodeFileTree,
        updateField: state.updateField,
        closeFile: state.closeFile,
      }))
    )

  // 固定「预览」+ operation.tabList 里追加的文件 tab
  const tabs = useMemo<TabItem[]>(() => [PREVIEW_TAB, ...tabList], [tabList])

  const setTabHandle = (tab: string) => {
    updateField({ currentTab: tab })
  }

  const renderPanel = () => {
    if (!isHydrated) return null
    if (currentTab === "preview") return <Preview />
    if (isCodeEditorTab(currentTab)) {
      // 文件 tab 的 label 就是路径，内容挂在 item 上
      const tab = tabList.find((item) => item.value === currentTab)
      if (!tab) return null
      return <CodeEditor path={tab.label} content={tab.content ?? ""} />
    }
    return null
  }

  return (
    <div className="flex flex-1 py-2 pr-2">
      {isHydrated && showCodeFileTree && <Filetree />}
      <div className="flex flex-1 flex-col">
        <Header
          tabList={tabs}
          tab={currentTab}
          setTab={setTabHandle}
          closeTab={closeFile}
        />
        {renderPanel()}
      </div>
    </div>
  )
}

export default Right

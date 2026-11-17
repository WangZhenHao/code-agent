"use client"

import { useMemo } from "react"

import Header, { type TabItem } from "./header"
import Preview from "./preview"
import CodeEditor from "./code-editor"
import Filetree from "./file-tree"
import {
  PREVIEW_TAB,
  useProjectOperateHydrated,
  useProjectOperateStore,
} from "@/store/project-operate"

/** 演示数据：文件树接上接口后删掉，内容改从接口拉 */
const MOCK_FILE = {
  path: "app/config.ts",
  content: `// 配置文件
export const config = {
  apiUrl: "https://api.example.com",
  timeout: 5000
}`,
}

const Right = () => {
  const isHydrated = useProjectOperateHydrated()
  const currentTab = useProjectOperateStore(
    (state) => state.operation.currentTab
  )
  const tabList = useProjectOperateStore((state) => state.operation.tabList)
  const showCodeFileTree = useProjectOperateStore(
    (state) => state.operation.showCodeFileTree
  )
  const updateField = useProjectOperateStore((state) => state.updateField)

  // 固定「预览」+ operation.tabList 里追加的文件 tab
  const tabs = useMemo<TabItem[]>(() => [PREVIEW_TAB, ...tabList], [tabList])

  const setTabHandle = (tab: string) => {
    updateField({ currentTab: tab })
  }

  const renderPanel = () => {
    if (!isHydrated) return null
    if (currentTab === "preview") return <Preview />
    if (currentTab === "codeEditor") {
      return <CodeEditor path={MOCK_FILE.path} content={MOCK_FILE.content} />
    }
    return null
  }

  return (
    <div className="flex flex-1 py-2 pr-2">
      {isHydrated && showCodeFileTree && <Filetree />}
      <div className="flex flex-1 flex-col">
        <Header tabList={tabs} tab={currentTab} setTab={setTabHandle} />
        {renderPanel()}
      </div>
    </div>
  )
}

export default Right

"use client"

import { useState } from "react"

import { AppWindow, FileCode } from "lucide-react"
import Header, { type TabItem } from "./header"
import Preview from "./preview"
import CodeEditor from "./code-editor"
import Filetree from "./file-tree"

// 先写死演示数据，等文件树接上接口再由选中节点驱动
const MOCK_FILE = {
  path: "app/config.ts",
  content: `// 配置文件
export const config = {
  apiUrl: "https://api.example.com",
  timeout: 5000
}`,
}

const Right = () => {
  const [currentTab, setCurrentTab] = useState("preview")
  const [tabList] = useState<TabItem[]>([
    { value: "preview", label: "预览", icon: AppWindow },
    { value: "codeEditor", label: MOCK_FILE.path, icon: FileCode },
  ])

  const renderPanel = () => {
    if (currentTab === "preview") {
      return <Preview />
    } else if (currentTab === "codeEditor") {
      return <CodeEditor path={MOCK_FILE.path} content={MOCK_FILE.content} />
    }
    return null
  }

  return (
    <div className="flex flex-1 py-2 pr-2">
      <Filetree />
      <div className="flex flex-1 flex-col">
        <Header tabList={tabList} tab={currentTab} setTab={setCurrentTab} />
        {renderPanel()}
      </div>
    </div>
  )
}

export default Right

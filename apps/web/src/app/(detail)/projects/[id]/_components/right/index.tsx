"use client"

import { useState } from "react"
import Header from "./header"
import Preview from "./preview"
import Filetree from "./file-tree"

const Right = () => {
  const [currentTab, setCurrentTab] = useState("preview")
  const [tabList, setTabList] = useState<{ value: string; label: string }[]>([
    { value: "preview", label: "预览" },
  ])
  return (
    <div className="flex flex-1 pr-2 py-2">
      <Filetree />
      <div className="flex flex-1 flex-col">
        <Header tabList={tabList} tab={currentTab} setTab={setCurrentTab} />
        <Preview />
      </div>
    </div>
  )
}

export default Right

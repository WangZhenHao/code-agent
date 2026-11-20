"use client"

import { ExternalLink, AppWindow } from "lucide-react"
import { FileIcon } from "@react-symbols/icons/utils"

import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useProjectDetailStore } from "@/store/project-detail"

/**
 * tab 图标的判别串。存成字符串（而不是组件）才能跟着 tabList 一起持久化，
 * 渲染时再按类型映射到具体组件；`path` 用文件类型图标，按 label 的扩展名取。
 */
export type TabIcon = "preview" | "path"

/** 预览面板顶栏：标签切换 + 新建标签 + 右侧工具区（主题、面板、协作、部署）。 */
export type TabItem = {
  value: string
  label: string
  icon: TabIcon
  /** 文件 tab 的内容，打开时由 `file.read` 拉取 */
  content?: string
  canClose?: boolean
}

const TabIconView = ({ icon, label }: { icon: TabIcon; label: string }) => {
  if (icon === "path") {
    return (
      <FileIcon
        fileName={label}
        autoAssign
        data-icon="inline-start"
        className="size-4 shrink-0"
      />
    )
  }
  return <AppWindow data-icon="inline-start" />
}

const Header = ({
  tab,
  setTab,
  tabList,
}: {
  tab: string
  setTab: (tab: string) => void
  tabList: TabItem[]
}) => {
  const projectInfo = useProjectDetailStore((state) => state.info)
  const opendHandle = () => {
    if (projectInfo?.preview_url) {
      window.open(projectInfo.preview_url, "_blank")
    }
  }
  return (
    <div className="flex h-11 shrink-0 items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList variant="line">
            {tabList.map(({ value, label, icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="cursor-pointer data-active:bg-muted dark:data-active:bg-muted"
              >
                <TabIconView icon={icon} label={label} />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              onClick={opendHandle}
              variant="ghost"
              size="icon-sm"
              aria-label="在新窗口打开"
            >
              <ExternalLink />
            </Button>
          </TooltipTrigger>
          <TooltipContent>在新窗口打开</TooltipContent>
        </Tooltip>
        <Button size="sm">部署</Button>
      </div>
    </div>
  )
}

export default Header

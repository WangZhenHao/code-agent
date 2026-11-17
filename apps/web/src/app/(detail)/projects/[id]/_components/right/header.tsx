"use client"

import { ExternalLink, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useProjectDetailStore } from "@/store/project-detail"

/** 预览面板顶栏：标签切换 + 新建标签 + 右侧工具区（主题、面板、协作、部署）。 */
export type TabItem = {
  value: string
  label: string
  icon: LucideIcon
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
            {tabList.map(({ value, label, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="cursor-pointer data-active:bg-muted dark:data-active:bg-muted"
              >
                <Icon data-icon="inline-start" />
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

"use client"

import { ExternalLink, AppWindow, XIcon } from "lucide-react"
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
  closeTab,
}: {
  tab: string
  setTab: (tab: string) => void
  tabList: TabItem[]
  /** 关闭可关闭的 tab（`canClose`）。预览是固定 tab，不传关闭入口。 */
  closeTab: (value: string) => void
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
            {tabList.map(({ value, label, icon, canClose }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="group/tab cursor-pointer data-active:bg-muted dark:data-active:bg-muted"
              >
                <TabIconView icon={icon} label={label} />
                {label}
                {canClose && (
                  // TabsTrigger 渲染出来就是 <button>，里面不能再嵌 button，
                  // 所以关闭图标用 span 顶替按钮。mousedown 也要拦住——Radix
                  // 的 tab 是在 mousedown 时切换的，只拦 click 会先把 tab 激活再关掉。
                  <span
                    role="button"
                    tabIndex={-1}
                    aria-label={`关闭 ${label}`}
                    onMouseDown={(event) => {
                      event.preventDefault()
                      event.stopPropagation()
                    }}
                    onClick={(event) => {
                      event.preventDefault()
                      event.stopPropagation()
                      closeTab(value)
                    }}
                    className="inline-flex size-4 shrink-0 cursor-pointer items-center justify-center rounded-sm text-muted-foreground opacity-0 transition-opacity group-hover/tab:opacity-100 group-data-active/tab:opacity-100 hover:bg-foreground/10 hover:text-foreground"
                  >
                    <XIcon className="size-3.5" />
                  </span>
                )}
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

"use client"

import { useRouter } from "next/navigation"
import { ChevronLeft, Folder } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useProjectDetailStore } from "@/store/project-detail"
import { useProjectOperateStore } from "@/store/project-operate"

const LeftHeader = ({ className = "" }: { className?: string }) => {
  const router = useRouter()
  const projectInfo = useProjectDetailStore((state) => state.info)
  const toggleCodeFileTree = useProjectOperateStore(
    (state) => state.toggleCodeFileTree
  )
  return (
    <div
      className={`flex h-14 shrink-0 items-center px-0 py-3 text-foreground ${className}`}
    >
      <div className="flex flex-1 items-center justify-between">
        {/* 不能用 router.back()：预览 iframe 的导航会混进联合历史，后退会先退回 iframe 的上一页 */}
        <div className="flex items-center">
          <div
            className="cursor-pointer"
            onClick={() => router.push("/projects")}
          >
            <ChevronLeft />
          </div>
          <div className="min-w-30 pl-3 text-sm">
            {projectInfo?.title || ""}
          </div>
        </div>
        <div className="flex items-center gap-2 pr-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <Folder
                className="cursor-pointer"
                size={18}
                aria-label="文件树"
                onClick={toggleCodeFileTree}
              />
            </TooltipTrigger>
            <TooltipContent>文件树</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}

export default LeftHeader

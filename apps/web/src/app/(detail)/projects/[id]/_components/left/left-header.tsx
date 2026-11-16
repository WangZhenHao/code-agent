"use client"

import { useRouter } from "next/navigation"
import { ChevronLeft } from "lucide-react"
import { useProjectDetailStore } from "@/store/project-detail"

const LeftHeader = ({ className = "" }: { className?: string }) => {
  const router = useRouter()
  const projectInfo = useProjectDetailStore((state) => state.info)
  return (
    <div
      className={`flex h-14 shrink-0 items-center px-0 py-3 text-foreground ${className}`}
    >
      <div className="flex flex-1 items-center">
        {/* 不能用 router.back()：预览 iframe 的导航会混进联合历史，后退会先退回 iframe 的上一页 */}
        <div
          className="cursor-pointer"
          onClick={() => router.push("/projects")}
        >
          <ChevronLeft />
        </div>
        <div className="pl-3">{projectInfo?.title || ""}</div>
      </div>
    </div>
  )
}

export default LeftHeader

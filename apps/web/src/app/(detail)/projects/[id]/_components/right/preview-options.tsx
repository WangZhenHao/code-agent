"use client"

import {
  ArrowLeft,
  ArrowRight,
  Copy,
  Monitor,
  Power,
  RefreshCw,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useProjectDetailStore } from "@/store/project-detail"
import { toast } from "sonner"
import { useCopyToClipboard } from "usehooks-ts"

/**
 * 预览工具栏：前进/后退、地址栏、设备切换、编辑/刷新/旋转。
 * 目前是静态壳，地址栏还没有接后端数据。
 */
const PreviewOptions = ({ onRefresh }: { onRefresh?: () => void }) => {
  const projectInfo = useProjectDetailStore((state) => state.info)
  const [, copyToClipboard] = useCopyToClipboard()

  /** 明文 HTTP 下 navigator.clipboard 不存在，退回 textarea + execCommand */
  const legacyCopy = (text: string) => {
    const ta = document.createElement("textarea")
    ta.value = text
    ta.setAttribute("readonly", "")
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0"
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand("copy")
    document.body.removeChild(ta)
    return ok
  }

  const copyHandle = async () => {
    const url = projectInfo?.preview_url
    if (!url) return
    if ((await copyToClipboard(url)) || legacyCopy(url)) {
      toast.success("已复制到剪切板")
    } else {
      toast.error("复制失败，请手动选择地址")
    }
  }

  return (
    <div className="flex h-10 shrink-0 items-center gap-1 border-b bg-white px-2">
      <Button variant="ghost" size="icon-sm" aria-label="后退">
        <ArrowLeft />
      </Button>
      <Button variant="ghost" size="icon-sm" aria-label="前进">
        <ArrowRight />
      </Button>

      <InputGroup className="mx-1 h-8 flex-1 rounded-lg border-transparent bg-muted/60 dark:bg-muted/40">
        <InputGroupInput
          // defaultValue={url ?? ""}
          placeholder="输入 URL..."
          className="text-sm"
          aria-label="预览地址"
        />
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            onClick={() => void copyHandle()}
            size="icon-xs"
            aria-label="复制地址"
          >
            <Copy />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="设备模式">
            <Monitor />
          </Button>
        </TooltipTrigger>
        <TooltipContent>设备模式</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="刷新预览"
            onClick={onRefresh}
          >
            <RefreshCw />
          </Button>
        </TooltipTrigger>
        <TooltipContent>刷新预览</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="重启服务">
            <Power />
          </Button>
        </TooltipTrigger>
        <TooltipContent>重启服务</TooltipContent>
      </Tooltip>
    </div>
  )
}

export default PreviewOptions

"use client";

import {
  ArrowLeft,
  ArrowRight,
  Copy,
  Monitor,
  PenLine,
  Power,
  RefreshCw,
  RotateCcw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * 预览工具栏：前进/后退、地址栏、设备切换、编辑/刷新/旋转。
 * 目前是静态壳，`url` 有值时地址栏显示后端推送的 preview_url。
 */
const PreviewOptions = ({
  url,
  onRefresh,
}: {
  url?: string | null;
  onRefresh?: () => void;
}) => {
  return (
    <div className="flex h-10 shrink-0 items-center gap-1 px-2">
      <Button variant="ghost" size="icon-sm" aria-label="后退">
        <ArrowLeft />
      </Button>
      <Button variant="ghost" size="icon-sm" aria-label="前进">
        <ArrowRight />
      </Button>

      <InputGroup className="mx-1 h-8 flex-1 rounded-lg border-transparent bg-muted/60 dark:bg-muted/40">
        <InputGroupInput
          defaultValue={url ?? ""}
          placeholder="输入 URL..."
          className="text-sm"
          aria-label="预览地址"
        />
        <InputGroupAddon align="inline-end">
          <InputGroupButton size="icon-xs" aria-label="复制地址">
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
  );
};

export default PreviewOptions;

"use client";

import { useState } from "react";

import {
  AppWindow,
  ExternalLink,
  LayoutPanelLeft,
  PanelTop,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sun,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/** 预览面板顶栏：标签切换 + 新建标签 + 右侧工具区（主题、面板、协作、部署）。 */
const Header = () => {
  const [tab, setTab] = useState("preview");

  return (
    <div className="flex h-11 shrink-0 items-center justify-between gap-2 px-2">
      <div className="flex min-w-0 items-center gap-1">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList variant="line">
            <TabsTrigger
              value="preview"
              className="data-active:bg-muted dark:data-active:bg-muted"
            >
              <AppWindow data-icon="inline-start" />
              预览
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="在新窗口打开">
              <ExternalLink />
            </Button>
          </TooltipTrigger>
          <TooltipContent>在新窗口打开</TooltipContent>
        </Tooltip>
        <Button size="sm">部署</Button>
      </div>
    </div>
  );
};

export default Header;

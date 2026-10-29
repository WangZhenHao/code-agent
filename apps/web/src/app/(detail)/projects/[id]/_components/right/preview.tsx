"use client";

import {
  Bot,
  PanelBottom,
  PanelLeft,
  PanelTop,
  Search,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Empty, EmptyContent, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";

interface Shortcut {
  icon: LucideIcon;
  label: string;
  mac: [string, string];
  win: [string, string];
}

const SHORTCUTS: Shortcut[] = [
  { icon: Search, label: "快速检索代码内容", mac: ["⌘", "K"], win: ["Ctrl", "K"] },
  { icon: PanelLeft, label: "切换文件目录可见性", mac: ["⌘", "B"], win: ["Alt", "B"] },
  { icon: PanelBottom, label: "切换底部面板可见性", mac: ["⌘", "J"], win: ["Alt", "J"] },
  { icon: PanelTop, label: "打开新的默认标签页", mac: ["⌘", "N"], win: ["Alt", "N"] },
];

/**
 * 预览区。`status` 为 `ready` 且拿到 `url` 时渲染 iframe，
 * 否则显示点阵背景 + 空态（快捷键提示）。
 */
const Preview = ({ status, url }: { status: string; url?: string | null }) => {
  if (url && status === "ready") {
    return (
      <div className="min-h-0 flex-1 overflow-hidden rounded-t-lg border-t bg-background">
        <iframe src={url} title="预览" className="size-full border-0" />
      </div>
    );
  }

  return (
    <div className="relative min-h-0 flex-1 overflow-hidden bg-background">
      {/* 点阵背景 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(var(--border)_1px,transparent_1px)] bg-[size:16px_16px] mask-[radial-gradient(ellipse_at_center,black_35%,transparent_78%)]"
      />
      <div className="relative flex size-full items-center justify-center px-6">
        <Empty className="border-0">
          <EmptyHeader>
            <EmptyMedia>
              <Bot className="size-7 stroke-[1.5] text-foreground" />
            </EmptyMedia>
            <EmptyTitle className="flex items-center gap-1.5 text-muted-foreground">
              {status === "ready" ? "预览已就绪" : "预览准备中"}
              <Spinner className="size-3.5" />
            </EmptyTitle>
          </EmptyHeader>

          <EmptyContent className="max-w-xs gap-3">
            {SHORTCUTS.map(({ icon: Icon, label, mac, win }) => (
              <div key={label} className="flex w-full items-center gap-3">
                <Icon className="size-4 shrink-0 text-muted-foreground" />
                <KbdGroup className="min-w-16 flex-col items-stretch">
                  <div className="flex items-center gap-1">
                    <Kbd>{mac[0]}</Kbd>
                    <Kbd>{mac[1]}</Kbd>
                  </div>
                  <div className="flex items-center gap-1">
                    <Kbd>{win[0]}</Kbd>
                    <Kbd>{win[1]}</Kbd>
                  </div>
                </KbdGroup>
                <span className="ml-auto text-xs text-muted-foreground">
                  {label}
                </span>
              </div>
            ))}
          </EmptyContent>
        </Empty>
      </div>
    </div>
  );
};

export default Preview;

"use client";

import PreviewLoading from "./preview-loading";

/**
 * 预览区。`status` 为 `ready` 且拿到 `url` 时渲染 iframe，
 * 否则显示占位（点阵背景 + 快捷键提示）。
 */
const Preview = ({ status, url }: { status: string; url?: string | null }) => {
  const ready = status === "ready";

  if (url && ready) {
    return (
      <div className="min-h-0 flex-1 overflow-hidden rounded-t-lg border-t bg-background">
        <iframe src={url} title="预览" className="size-full border-0" />
      </div>
    );
  }

  return <PreviewLoading ready={ready} />;
};

export default Preview;

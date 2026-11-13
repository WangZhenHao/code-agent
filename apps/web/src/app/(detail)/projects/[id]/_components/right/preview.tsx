"use client"

import PreviewLoading from "./preview-loading"

/**
 * 预览区。`enabled`（后端 `preview_enabled`）且拿到 `url` 时渲染 iframe，
 * 否则显示占位（点阵背景 + 快捷键提示）。
 */
const Preview = ({
  enabled,
  url,
}: {
  enabled: boolean
  url?: string | null
}) => {
  if (url && enabled) {
    return (
      <div className="min-h-0 flex-1 overflow-hidden border-t bg-background">
        <iframe src={url} title="预览" className="size-full border-0" />
      </div>
    )
  }

  return <PreviewLoading ready={enabled} />
}

export default Preview

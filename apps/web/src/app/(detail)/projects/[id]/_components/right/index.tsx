"use client";

import { useState } from "react";

import { useWs, useWsEvent } from "@/components/providers/ws-provider";

/**
 * 预览面板。数据来源是后端推送 `web.server_status_changed`
 * （params.preview 与 `preview.status` 应答同形状）；刚连上时可以发一次
 * `preview.status` 补齐当前快照——推送是尽力而为，丢了不会重发。
 */
const Right = () => {
  const { sendWs } = useWs();
  const [previewStatus, setPreviewStatus] = useState<string>("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useWsEvent("web.server_status_changed", (params) => {
    const preview = params.preview;
    if (preview && typeof preview === "object") {
      const p = preview as Record<string, unknown>;
      if (typeof p.status === "string") setPreviewStatus(p.status);
      setPreviewUrl(typeof p.preview_url === "string" ? p.preview_url : null);
    }
  });

  return (
    <div className="flex-1 flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">预览状态</span>
        <span className="text-sm">{previewStatus}</span>
      </div>
      {previewUrl && (
        <a className="text-sm underline" href={previewUrl} target="_blank" rel="noreferrer">
          {previewUrl}
        </a>
      )}
      <button
        type="button"
        className="self-start rounded border px-3 py-1 text-sm"
        onClick={() => sendWs("preview.status", {})}
      >
        刷新预览状态
      </button>
    </div>
  );
};

export default Right;

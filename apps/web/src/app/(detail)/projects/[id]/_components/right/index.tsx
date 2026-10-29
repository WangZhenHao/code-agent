"use client";

import { useState } from "react";

import { useWs, useWsEvent } from "@/components/providers/ws-provider";

import Header from "./header";
import Preview from "./preview";
import PreviewOptions from "./preview-options";

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
    <div className="flex min-w-0 flex-1 flex-col bg-background">
      <Header />
      <PreviewOptions
        url={previewUrl}
        onRefresh={() => sendWs("preview.status", {})}
      />
      <Preview status={previewStatus} url={previewUrl} />
    </div>
  );
};

export default Right;

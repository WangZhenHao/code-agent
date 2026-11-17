"use client"

import type { EditorProps } from "@monaco-editor/react"
import dynamic from "next/dynamic"

/** 首屏下载 monaco 时的占位。 */
const FileLoading = () => (
  <div className="flex size-full items-center justify-center bg-white text-sm text-muted-foreground">
    编辑器加载中…
  </div>
)

// monaco 只能跑在浏览器里（worker + DOM），关掉 SSR。
// dynamic 推不出默认导出的 props，泛型显式标成 EditorProps。
const Editor = dynamic<EditorProps>(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: FileLoading,
})

/** 按扩展名猜 monaco 语言；认不出的当纯文本。 */
const EXT_LANGUAGE: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  json: "json",
  md: "markdown",
  css: "css",
  html: "html",
  py: "python",
  yaml: "yaml",
  yml: "yaml",
  sh: "shell",
  txt: "plaintext",
}

const getLanguage = (path: string) => {
  const ext = path.split(".").pop()?.toLowerCase() ?? ""
  return EXT_LANGUAGE[ext] ?? "plaintext"
}

/**
 * 代码编辑器面板。
 * `path` 决定语言高亮和 model 的 URI，`content` 是文件内容；
 * 传 `onChange` 才可编辑，否则只读。
 */
const CodeEditor = ({
  path,
  content,
  onChange,
}: {
  path: string
  content: string
  onChange?: (value: string) => void
}) => {
  return (
    <div className="min-h-0 flex-1 overflow-hidden rounded-xl border bg-white">
      <Editor
        path={path}
        value={content}
        language={getLanguage(path)}
        theme="vs"
        onChange={(value) => onChange?.(value ?? "")}
        options={{
          readOnly: !onChange,
          fontSize: 13,
          lineHeight: 20,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 12 },
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
        }}
      />
    </div>
  )
}

export default CodeEditor

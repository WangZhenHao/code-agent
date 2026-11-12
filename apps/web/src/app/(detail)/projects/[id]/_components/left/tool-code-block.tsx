"use client"

import Markdown from "@/components/custom/markdown"
import { cn } from "@/lib/utils"

const asString = (value: unknown) => (typeof value === "string" ? value : "")

/**
 * 工具调用里的代码展示：把纯文本（文件内容 / shell 输出）包成围栏代码块交给 Markdown，
 * 换行、空白原样保留，长行由 markdown 的 pre 横向滚动兜住。
 *
 * 围栏长度按内容里最长的反引号串加一取，避免输出里自带 ``` 把块提前闭合。
 * `language` 不传就是纯文本；传了但 lowlight 不认识时会被 rehype-highlight 的
 * `ignoreMissing` 忽略，同样退回纯文本。
 */
export const ToolCodeBlock = ({
  code,
  language,
  className,
}: {
  code: string
  language?: string
  className?: string
}) => (
  <div className={cn("overflow-auto", className)}>
    <Markdown text={toCodeBlock(code, language)} />
  </div>
)

/** 工具结果该按什么语言高亮：bash 的输出就是 shell 脚本，文件类工具看读写路径的扩展名，搜索类工具是普通文本、不上色。 */
export const resultLanguage = (name: string, args: Record<string, unknown>) => {
  if (name === "bash") return "bash"
  return fileLanguage(args)
}

/**
 * 路径的扩展名直接当语言名用——lowlight 注册了 ts/tsx/py/yml/md/h 这类别名，
 * 认不出的会退回纯文本。
 */
export const fileLanguage = (args: Record<string, unknown>) => {
  const path = asString(args.file_path) || asString(args.path)
  if (!path) return undefined
  const base = path.split("/").pop() ?? ""
  return base.includes(".") ? base.split(".").pop()?.toLowerCase() : undefined
}

const toCodeBlock = (text: string, language?: string) => {
  const runs: string[] = text.match(/`+/g) ?? []
  const longest = runs.reduce((max, run) => Math.max(max, run.length), 0)
  const fence = "`".repeat(Math.max(3, longest + 1))
  return `${fence}${language ?? ""}\n${text}\n${fence}`
}

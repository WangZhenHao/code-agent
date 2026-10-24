"use client";

import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * 模型输出的 Markdown 渲染。
 *
 * 项目没有装 `@tailwindcss/typography`，所以这里不用 `prose`，而是把每个
 * 元素显式映射成 Tailwind 类，保证在流式输出时样式稳定、和气泡排版一致。
 *
 * 代码块不做语法高亮（没有装高亮插件），只区分行内 code 和围栏代码块：
 * 行内用 `[pre_&]` 变体把自己还原成透明背景。
 */

const components: Components = {
  p: ({ children }) => (
    <p className="mt-3 first:mt-0 leading-relaxed break-words">{children}</p>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-primary underline underline-offset-2 break-all"
    >
      {children}
    </a>
  ),
  h1: ({ children }) => (
    <h1 className="mt-5 mb-2 text-lg font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-5 mb-2 text-base font-semibold first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-4 mb-1.5 text-sm font-semibold first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="mt-3 mb-1 font-semibold first:mt-0">{children}</h4>
  ),
  ul: ({ children }) => (
    <ul className="mt-2 list-disc space-y-1 pl-5 first:mt-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mt-2 list-decimal space-y-1 pl-5 first:mt-0">{children}</ol>
  ),
  li: ({ children }) => <li className="break-words">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mt-3 border-l-2 border-border pl-3 text-muted-foreground first:mt-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  img: ({ src, alt }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={typeof src === "string" ? src : undefined}
      alt={alt ?? ""}
      className="mt-2 max-w-full rounded-md"
    />
  ),
  pre: ({ children }) => (
    <pre className="mt-3 overflow-x-auto rounded-md border border-border bg-muted/60 p-3 text-xs leading-relaxed first:mt-0">
      {children}
    </pre>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] [pre_&]:rounded-none [pre_&]:bg-transparent [pre_&]:p-0 [pre_&]:text-xs">
      {children}
    </code>
  ),
  // 表格横向滚动交给外层容器，避免撑破消息气泡
  table: ({ children }) => (
    <div className="mt-3 overflow-x-auto first:mt-0">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted/60 px-2 py-1 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-2 py-1 align-top">{children}</td>
  ),
};

const Markdown = ({ text, className }: { text: string; className?: string }) => {
  return (
    <div className={cn("text-sm break-words", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
};

// 消息列表里其它气泡不随流式 token 变化，跳过重复解析
export default memo(Markdown);

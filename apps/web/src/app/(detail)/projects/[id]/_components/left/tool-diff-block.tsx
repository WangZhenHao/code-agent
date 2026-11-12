"use client"

import { useMemo } from "react"

import { type Change, diffLines, diffWordsWithSpace } from "diff"

import { cn } from "@/lib/utils"

/**
 * `edit_file` 的改动预览：一对 `-` / `+` 行，行内再按词高亮真正变化的片段。
 *
 * 按行先 diff，再对「一整块删除 + 紧接着一整块新增」的相邻对做词级 diff，
 * 这样只挪动了一行的场景不会整行标红标绿，能看出具体改了几个词。
 */

type LineKind = "add" | "remove" | "context"

interface Segment {
  text: string
  changed: boolean
}

interface Line {
  kind: LineKind
  segments: Segment[]
}

function toLines(kind: LineKind, parts: Segment[]): Line[] {
  const lines: Line[] = [{ kind, segments: [] }]
  for (const part of parts) {
    const pieces = part.text.split("\n")
    pieces.forEach((piece, index) => {
      if (index > 0) lines.push({ kind, segments: [] })
      if (piece)
        lines[lines.length - 1].segments.push({
          text: piece,
          changed: part.changed,
        })
    })
  }
  if (lines.length > 1 && lines[lines.length - 1].segments.length === 0) {
    lines.pop()
  }
  return lines
}

function pairedLines(removed: string, added: string): Line[] {
  const words = diffWordsWithSpace(removed, added)
  const removedSide = words
    .filter((part) => !part.added)
    .map((part) => ({ text: part.value, changed: Boolean(part.removed) }))
  const addedSide = words
    .filter((part) => !part.removed)
    .map((part) => ({ text: part.value, changed: Boolean(part.added) }))
  return [...toLines("remove", removedSide), ...toLines("add", addedSide)]
}

function buildLines(oldString: string, newString: string): Line[] {
  const chunks: Change[] = diffLines(oldString, newString)
  const lines: Line[] = []

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i]
    const next = chunks[i + 1]

    if (chunk.removed && next?.added) {
      lines.push(...pairedLines(chunk.value, next.value))
      i++
      continue
    }

    const kind: LineKind = chunk.added
      ? "add"
      : chunk.removed
        ? "remove"
        : "context"
    lines.push(...toLines(kind, [{ text: chunk.value, changed: false }]))
  }

  return lines
}

const LINE_STYLE: Record<LineKind, string> = {
  add: "bg-success/10 text-success",
  remove: "bg-destructive/10 text-destructive",
  context: "text-muted-foreground",
}

const SEGMENT_STYLE: Record<LineKind, string> = {
  add: "rounded-[2px] bg-success/25",
  remove: "rounded-[2px] bg-destructive/25",
  context: "",
}

const MARKER: Record<LineKind, string> = { add: "+", remove: "-", context: " " }

export const ToolDiffBlock = ({
  oldString,
  newString,
}: {
  oldString: string
  newString: string
}) => {
  const lines = useMemo(
    () => buildLines(oldString, newString),
    [oldString, newString]
  )

  return (
    <div className="overflow-x-auto py-1 font-mono text-xs leading-relaxed">
      {lines.map((line, lineIndex) => (
        <div
          key={`line-${lineIndex}`}
          className={cn("flex px-2", LINE_STYLE[line.kind])}
        >
          <span className="w-3 shrink-0 opacity-60 select-none">
            {MARKER[line.kind]}
          </span>
          <span className="break-all whitespace-pre-wrap">
            {line.segments.length === 0
              ? " "
              : line.segments.map((segment, segmentIndex) => (
                  <span
                    key={`segment-${lineIndex}-${segmentIndex}`}
                    className={
                      segment.changed ? SEGMENT_STYLE[line.kind] : undefined
                    }
                  >
                    {segment.text}
                  </span>
                ))}
          </span>
        </div>
      ))}
    </div>
  )
}

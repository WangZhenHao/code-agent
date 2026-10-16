"use client"

import * as React from "react"

import {
  ArrowUpIcon,
  CheckIcon,
  ChevronDownIcon,
  PlusIcon,
  Settings2Icon,
  ZapIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"

export type Mode = "agent" | "plan"

const MODES: Array<{ id: Mode; label: string }> = [
  { id: "agent", label: "agent模式" },
  { id: "plan", label: "plan模式" },
]

export function Composer({
  examples,
  mode,
  modeLabel,
  onModeChange,
  prompt,
  onPromptChange,
  onCreate,
  submitting,
}: {
  examples: string[]
  mode: Mode
  modeLabel: string
  onModeChange: (mode: Mode) => void
  prompt: string
  onPromptChange: (prompt: string) => void
  onCreate: () => void
  submitting: boolean
}) {
  const placeholder = useAnimatedPlaceholder(examples, prompt.length > 0)

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (prompt.trim()) onCreate()
      }}
      className="mt-7 max-w-300 text-left"
    >
      <InputGroup className="gap-0 rounded-2xl border-border/80 bg-card py-0 shadow-xs">
        <InputGroupTextarea
          rows={3}
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          placeholder={placeholder}
          aria-label="描述你想创建的应用"
          className="min-h-24 w-200 px-4 py-4 leading-6"
        />

        <InputGroupAddon
          align="block-end"
          className="gap-1.5 px-4 pb-2 text-muted-foreground"
        >
          <InputGroupButton size="icon-sm" aria-label="添加附件">
            <PlusIcon />
          </InputGroupButton>
          <InputGroupButton size="icon-sm" aria-label="参数设置">
            <Settings2Icon />
          </InputGroupButton>
          <InputGroupButton size="sm" className="gap-1.5 px-2">
            <ZapIcon />
            技能
            <span className="text-muted-foreground">12</span>
          </InputGroupButton>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <InputGroupButton size="sm" className="gap-1 px-2">
                {modeLabel}
                <ChevronDownIcon />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-36">
              <DropdownMenuGroup>
                {MODES.map((item) => (
                  <DropdownMenuItem
                    key={item.id}
                    onSelect={() => onModeChange(item.id)}
                    className="justify-between"
                  >
                    {item.label}
                    {mode === item.id ? <CheckIcon /> : null}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            type="submit"
            size="icon"
            disabled={prompt.trim().length === 0 || submitting}
            aria-label={submitting ? "正在创建" : "创建"}
            className="ml-auto rounded-full bg-foreground text-background hover:bg-foreground/80 disabled:opacity-40"
          >
            <ArrowUpIcon />
          </Button>
        </InputGroupAddon>
      </InputGroup>
    </form>
  )
}

function useAnimatedPlaceholder(examples: string[], hasText: boolean) {
  const [placeholder, setPlaceholder] = React.useState("")
  const [prefersReducedMotion, setPrefersReducedMotion] = React.useState(false)

  React.useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setPrefersReducedMotion(media.matches)
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])

  React.useEffect(() => {
    if (prefersReducedMotion || hasText) return

    let exampleIndex = 0
    let characterIndex = 0
    let deleting = false
    let timer: number

    const step = () => {
      const example = examples[exampleIndex]
      if (deleting) {
        characterIndex = Math.max(0, characterIndex - 2)
        setPlaceholder(example.slice(0, characterIndex))
        if (characterIndex === 0) {
          deleting = false
          exampleIndex = (exampleIndex + 1) % examples.length
          timer = window.setTimeout(step, 300)
        } else {
          timer = window.setTimeout(step, 28)
        }
        return
      }

      characterIndex = Math.min(example.length, characterIndex + 1)
      setPlaceholder(example.slice(0, characterIndex))
      if (characterIndex === example.length) {
        deleting = true
        timer = window.setTimeout(step, 1600)
      } else {
        timer = window.setTimeout(step, 55)
      }
    }

    timer = window.setTimeout(step, 250)
    return () => window.clearTimeout(timer)
  }, [examples, hasText, prefersReducedMotion])

  return prefersReducedMotion ? examples[0] : placeholder
}

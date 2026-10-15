"use client"

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

const MODES = [
  { id: "agent", label: "agent模式" },
  { id: "plan", label: "plan模式" },
]

export function Composer({
  mode,
  modeLabel,
  onModeChange,
  prompt,
  onPromptChange,
}: {
  mode: string
  modeLabel: string
  onModeChange: (mode: string) => void
  prompt: string
  onPromptChange: (prompt: string) => void
}) {
  return (
    <form
      onSubmit={(event) => event.preventDefault()}
      className="mt-7 max-w-300 text-left"
    >
      <InputGroup className="gap-0 rounded-2xl border-border/80 bg-card py-0 shadow-xs">
        <InputGroupTextarea
          rows={3}
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          placeholder="帮我做一个旅行攻略网站，实现我输入旅行地点和旅游时间，生成旅行攻略和行李建议"
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
            aria-label="发送"
            disabled={prompt.trim().length === 0}
            className="ml-auto rounded-full bg-foreground text-background hover:bg-foreground/80 disabled:opacity-40"
          >
            <ArrowUpIcon />
          </Button>
        </InputGroupAddon>
      </InputGroup>
    </form>
  )
}

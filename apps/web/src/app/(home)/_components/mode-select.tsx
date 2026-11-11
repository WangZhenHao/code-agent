"use client"

import { CheckIcon, ChevronDownIcon } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { InputGroupButton } from "@/components/ui/input-group"
import { DEFAULT_MODE, MODES } from "@/lib/chat-options"
import { useAgentChatHydrated, useAgentChatStore } from "@/store/agent-chat"

/** 模式下拉框，选中项直接写回 agentChat store */
export function ModeSelect() {
  const hydrated = useAgentChatHydrated()
  const storedMode = useAgentChatStore((state) => state.mode)
  const setMode = useAgentChatStore((state) => state.setMode)
  // 持久化回填前先渲染默认值，避免 SSR 与客户端文案不一致
  const mode = hydrated ? storedMode : DEFAULT_MODE
  const modeLabel = MODES.find((item) => item.id === mode)?.label ?? mode

  return (
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
              onSelect={() => setMode(item.id)}
              className="justify-between"
            >
              {item.label}
              {mode === item.id ? <CheckIcon /> : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

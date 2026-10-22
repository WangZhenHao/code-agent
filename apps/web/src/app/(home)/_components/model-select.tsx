"use client"

import { CheckIcon, ChevronDownIcon } from "lucide-react"
import * as React from "react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { InputGroupButton } from "@/components/ui/input-group"
import { DEFAULT_MODEL, MODELS, groupModels } from "@/lib/chat-options"
import { useAgentChatHydrated, useAgentChatStore } from "@/store/agent-chat"

const MODEL_GROUPS = groupModels()

/** 模型下拉框，选中项直接写回 agentChat store */
export function ModelSelect() {
  const hydrated = useAgentChatHydrated()
  const storedModel = useAgentChatStore((state) => state.model)
  const setModel = useAgentChatStore((state) => state.setModel)
  // 持久化回填前先渲染默认值，避免 SSR 与客户端文案不一致
  const model = hydrated ? storedModel : DEFAULT_MODEL
  const modelLabel = MODELS.find((item) => item.id === model)?.label ?? model

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <InputGroupButton size="sm" className="gap-1 px-2">
          {modelLabel}
          <ChevronDownIcon />
        </InputGroupButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        {MODEL_GROUPS.map((group, index) => (
          <React.Fragment key={group.vendor}>
            {index > 0 ? <DropdownMenuSeparator /> : null}
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              {group.vendor}
            </DropdownMenuLabel>
            <DropdownMenuGroup>
              {group.items.map((item) => (
                <DropdownMenuItem
                  key={item.id}
                  onSelect={() => setModel(item.id)}
                  className="flex-col items-start gap-0.5"
                >
                  <span className="flex w-full items-center justify-between">
                    {item.label}
                    {model === item.id ? <CheckIcon /> : null}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {item.description}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </React.Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

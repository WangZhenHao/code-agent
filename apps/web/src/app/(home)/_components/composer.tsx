"use client"

import {
  ArrowUpIcon,
  CheckIcon,
  ChevronDownIcon,
  Loader2Icon,
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
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import React, { useRef, useState } from "react"
import type { ChatCreateChatCreatePostMutationVariables } from "@/api/generated/chat/chat"
import { MessageMode } from "@/api/generated/model/messageMode"
import { DEFAULT_MODEL, MODELS, MODES, groupModels } from "./maps"



export function Composer({
  loading = false,
  prompt,
  onPromptChange,
  onSubmit
}: {
  loading?: boolean
  prompt: string
  onPromptChange: (prompt: string) => void
  onSubmit?: (prompt: ChatCreateChatCreatePostMutationVariables['data']) => void
}) {
  const [mode, onModeChange] = useState<MessageMode>("agent")
  const [model, onModelChange] = useState<string>(DEFAULT_MODEL)
  const modeLabel = MODES.find((m) => m.id === mode)?.label
  const modelLabel = MODELS.find((m) => m.id === model)?.label ?? model
  const modelGroups = groupModels()
  const params = useRef<ChatCreateChatCreatePostMutationVariables['data']>({})

  const onSubmitHandle = (event: React.SubmitEvent<HTMLFormElement>) => {
    event.preventDefault()
    params.current = {
      mode: mode,
      model: model,
      parts: [{ type: 'text', text: prompt }]
    }
    onSubmit?.(params.current)
  }

  return (
    <form
      onSubmit={onSubmitHandle}
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
          {/* <InputGroupButton size="icon-sm" aria-label="参数设置">
            <Settings2Icon />
          </InputGroupButton>
          <InputGroupButton size="sm" className="gap-1.5 px-2">
            <ZapIcon />
            技能
            <span className="text-muted-foreground">12</span>
          </InputGroupButton> */}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <InputGroupButton size="sm" className="gap-1 px-2">
                {modelLabel}
                <ChevronDownIcon />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-60">
              {modelGroups.map((group, index) => (
                <React.Fragment key={group.vendor}>
                  {index > 0 ? <DropdownMenuSeparator /> : null}
                  <DropdownMenuLabel className="text-xs text-muted-foreground">
                    {group.vendor}
                  </DropdownMenuLabel>
                  <DropdownMenuGroup>
                    {group.items.map((item) => (
                      <DropdownMenuItem
                        key={item.id}
                        onSelect={() => onModelChange(item.id)}
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
                    onSelect={() => onModeChange(item.id as MessageMode)}
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
            disabled={prompt.trim().length === 0 || loading}
            aria-busy={loading}
            className="ml-auto rounded-full bg-foreground text-background hover:bg-foreground/80 disabled:opacity-40"
          >
            {loading ? <Loader2Icon className="animate-spin" /> : <ArrowUpIcon />}
          </Button>
        </InputGroupAddon>
      </InputGroup>
    </form>
  )
}

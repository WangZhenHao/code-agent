"use client"

import { ArrowUpIcon, Loader2Icon, PlusIcon } from "lucide-react"
import React, { useRef } from "react"

import { ModelSelect } from "@/app/(home)/_components/model-select"
import { ModeSelect } from "@/app/(home)/_components/mode-select"
import { Button } from "@/components/ui/button"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import type { ChatCreateChatCreatePostMutationVariables } from "@/api/generated/chat/chat"
import { useAgentChatStore } from "@/store/agent-chat"

type TypeParmas = ChatCreateChatCreatePostMutationVariables["data"]
export function Composer({
  loading = false,
  prompt,
  onPromptChange,
  onSubmit,
}: {
  loading?: boolean
  prompt: string
  onPromptChange: (prompt: string) => void
  onSubmit?: (prompt: TypeParmas) => void
}) {
  const params = useRef<TypeParmas>({})

  const onSubmitHandle = (event: React.SubmitEvent<HTMLFormElement>) => {
    event.preventDefault()
    // 提交时才读，避免 mode/model 变化触发整个表单重渲染
    const { mode, model } = useAgentChatStore.getState()
    params.current = {
      mode,
      model,
      parts: [{ type: "text", text: prompt }],
    }
    onSubmit?.(params.current)
  }

  return (
    <form onSubmit={onSubmitHandle} className="mt-7 max-w-300 text-left">
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

          <ModelSelect />
          <ModeSelect />

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

"use client"

import { ArrowUpIcon, Loader2Icon, PlusIcon } from "lucide-react"
import React from "react"

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

export type TypeParmas = ChatCreateChatCreatePostMutationVariables["data"]
export function Composer({
  loading = false,
  prompt,
  onPromptChange,
  onSubmit,
  className = '',
}: {
  loading?: boolean
  prompt: string
  onPromptChange: (prompt: string) => void
  onSubmit?: (prompt: TypeParmas) => void,
  className?: string
}) {
  const submit = () => {
    if (prompt.trim().length === 0 || loading) return
    // 提交时才读，避免 mode/model 变化触发整个表单重渲染
    const { mode, model } = useAgentChatStore.getState()
    onSubmit?.({
      mode,
      model,
      parts: [{ type: "text", text: prompt }],
    })
  }

  const onSubmitHandle = (event: React.SubmitEvent<HTMLFormElement>) => {
    event.preventDefault()
    submit()
  }

  const onKeyDownHandle = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 输入法组合中（如中文拼音候选）回车只用于选词，不提交
    if (event.nativeEvent.isComposing) return
    // 回车提交，Shift/Cmd+Enter 保留换行
    if (event.key === 'Enter' && !event.shiftKey && !event.metaKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={onSubmitHandle} className={`text-left ${className}`}>
      <InputGroup className="gap-0 rounded-2xl border-border/80 bg-card py-0 shadow-xs">
        <InputGroupTextarea
          rows={3}
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          placeholder="帮我做一个旅行攻略网站，实现我输入旅行地点和旅游时间，生成旅行攻略和行李建议"
          className="min-h-24 w-full px-4 py-4 leading-6"
          onKeyDown={onKeyDownHandle}
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

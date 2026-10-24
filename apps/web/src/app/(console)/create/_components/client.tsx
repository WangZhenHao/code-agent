"use client";

import { useChatCreateChatCreatePost } from "@/api/generated/chat/chat";
import { Composer } from "@/app/(home)/_components/composer";
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ChatCreateChatCreatePostMutationVariables } from "@/api/generated/chat/chat";

const Client = () => {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const { mutate, isPending, error } = useChatCreateChatCreatePost();
  const handleSumbit = (
    params: ChatCreateChatCreatePostMutationVariables["data"],
  ) => {
    mutate(
      { data: params },
      {
        onSuccess: (res) => {
          // create 接口会新建或复用会话，拿到 id 后直接进项目详情页
          router.push(`/projects/${res.id}`);
        },
      },
    );
  };

  return (
    <>
      <main className="relative flex flex-1 flex-col items-center px-4 pb-24 sm:px-6">
        <section className="mt-16 flex w-full max-w-3xl flex-col items-center text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-balance">
            码灵编程，你的 AI 开发伙伴
          </h1>
          <p className="mt-5 text-sm text-muted-foreground sm:text-lg">
            全栈、全流程、全托管式 AI 编程平台
          </p>

          <Composer
            className="w-200"
            loading={isPending}
            prompt={prompt}
            onPromptChange={setPrompt}
            onSubmit={handleSumbit}
          />

          {error && (
            <p className="mt-4 text-sm text-destructive">
              {error instanceof Error ? error.message : "创建失败，请稍后重试"}
            </p>
          )}
        </section>
      </main>
    </>
  );
};

export default Client;

"""自定义 agent 中间件。

带记账的 SummarizationMiddleware：除了原样转发压缩行为，还留下「本次调用到底发生了
什么」——这些信息在类外拿不到，只能在这里顺手记（压缩发生的那一刻，被压掉的消息就
不可逆了，事后再也恢复不出来）。

放在 helper/ 而不是节点里：它是可复用的中间件能力，与具体节点无关；code_agent 只是
它的第一个使用者。
"""

from langchain.agents.middleware import SummarizationMiddleware


class TrackingSummarization(SummarizationMiddleware):
    """带记账的 SummarizationMiddleware。

    除了原样转发压缩行为，它还把「本次调用到底发生了什么」留下来——这些信息在
    类外拿不到，只能在这里顺手记：

    - triggered：本次调用是否触发过压缩。
    - seen / input_ids：累积的消息快照，用来还原一份**完整的本轮对话**。

    用法：agent 跑完后，current_round_messages(final_messages) 就是本轮新增的全部
    消息，供落库与前端展示；agent 内部喂给模型的仍是压缩后的 messages，两者职责分开。
    """

    triggered: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 不能写成类属性：那样所有实例会共享同一个 dict。
        # 用 dict 而非 set/list：既要按 id 去重，又要保留首次出现的顺序。
        self._seen: dict = {}
        # 输入侧的 id 集合（历史 + 本轮用户输入）。第一次 before_model 见到的
        # state["messages"] 就是节点喂进来的 input_messages，据此记下即可，不必从外面传。
        self._input_ids: set = set()

    def _remember(self, messages):
        """在压缩**之前**把当前完整消息集记下来。

        为什么非记不可：result["messages"] 是子 agent 循环结束后的快照，而压缩是
        循环**中途**发生的。被压掉的消息在 result 里已不存在（原文被摘要模型吃进
        一段自然语言里，不可逆），事后无论怎么过滤都恢复不出来——本轮靠前的步骤
        会整段消失。before_model 每次都在压缩前进来，是唯一能看见它们的时刻。

        为什么要累积而不是每次覆盖：压缩会让 state["messages"] 变短（老历史换成
        一条 summary），只留最后一次快照等于又回到「丢消息」。累积则只增不减。

        反复 setdefault 是幂等的：同一批消息对象会在多次 before_model 里重复出现。
        """
        if not self._input_ids:
            # 首见即为输入侧全量，先记下来再往 _seen 里放。
            self._input_ids = {m.id for m in messages}
        for m in messages:
            self._seen.setdefault(m.id, m)

    def current_round_messages(self, final_messages):
        """还原本轮新增的全部消息（排除输入侧与压缩产生的合成摘要）。

        要**两个来源合并**，单独任何一个都会缺：

        - final_messages（result["messages"]）：循环结束时的快照。收尾消息（不再调
          工具的最终答复）在这里，但中途被压缩吃掉的本轮步骤已经不在里面了。
        - self._seen：每次 before_model 在压缩前累积的快照。中途步骤在这里，但它停在
          最后一次 before_model，收尾那几条还没产生。

        两边各自漏掉的正是对方有的，按 id 去重合并即是完整的本轮。顺序取 _seen 的首次
        出现序（即真实发生序），再把 final_messages 里 _seen 还没有的尾部补上。
        """
        def _is_round_message(m):
            return (
                m.id not in self._input_ids
                # 压缩产生的合成摘要不是本轮真实对话，不该落库或推给前端。
                and (m.additional_kwargs or {}).get("lc_source") != "summarization"
            )

        merged: dict = {}
        for m in self._seen.values():
            if _is_round_message(m):
                merged[m.id] = m
        for m in final_messages:
            if _is_round_message(m):
                merged.setdefault(m.id, m)   # 已有则不覆盖，保持首次出现顺序
        return list(merged.values())

    def before_model(self, state, runtime):
        self._remember(state["messages"])
        result = super().before_model(state, runtime)
        if result is not None:
            self.triggered = True
        return result

    async def abefore_model(self, state, runtime):
        # 节点走的是 ainvoke，实际生效的是这个；同步版本一并覆写，免得将来
        # 换回 invoke 时标志永远为 False —— 那种静默失效比报错难查得多。
        self._remember(state["messages"])
        result = await super().abefore_model(state, runtime)
        if result is not None:
            self.triggered = True
        return result

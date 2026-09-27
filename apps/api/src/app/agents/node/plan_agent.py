"""planAgent 节点：把需求拆成可执行的步骤清单。"""

from app.agents.node.state import State


def plan_agent(state: State) -> dict:
    """读用户需求，产出一份分步骤的计划。

    占位实现：不调模型，回一条固定消息便于确认图确实走到了这个节点。

    待接入 LLM 后：
    - 用 app.models.llm.get_model() 拿客户端（它会缓存，别在这里重复构造）；
    - 计划文本既写进 state["plan"]（供 codeAgent 结构化消费），
      也作为一条 assistant 消息追加进 messages（供前端流式展示）；
    - 如果这个节点以后变成多轮（读文件→再规划），要给它加循环边，
      而不是在函数里写 for 循环——那会挡住 LangGraph 的流式输出。
    """
    return {
        "messages": [{"role": "assistant", "content": "[planAgent] 占位：待接入规划 prompt"}],
        "plan": [],
    }

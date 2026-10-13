"""codeAgent 节点：按计划读写沙箱内文件。"""

from app.agents.helper.agent_prompt import generate_system_prompt
from app.agents.node.state import State
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from app.agents.tools import create_tools
from app.agents.tools._common import WORKSPACE
from app.api.sandbox.client.sandbox import get_sandbox_for_id
from app.db.models.session import Role
from app.models.llm import get_model
from langchain.messages import HumanMessage
from langchain_core.messages.utils import filter_messages
from langchain.agents.middleware import SummarizationMiddleware


async def code_agent(state: State, config: RunnableConfig):
    """agent 节点的核心逻辑：按计划读写沙箱内文件。

    签名带 config：LangGraph 会把父运行配置（含回调管理器）注入进来。透传它、
    并且用 ainvoke 而不是 invoke，子 agent 产出的 token 和工具结果才会流到外层
    的 messages 流里——本来它们全被 invoke 憋在节点内部，外层只剩一个最终结果。
    """
    session_id = state['session']['id']
    sandbox = get_sandbox_for_id(session_id)
    tools = create_tools(sandbox, mode=state['mode'])
    model = get_model(state['model'])
    system_prompt = generate_system_prompt(cwd=WORKSPACE, mode=state['mode'], project_context='')

    agent = create_agent(
        model=model, 
        tools=tools, 
        system_prompt=system_prompt,
        middleware=[
        SummarizationMiddleware(
                model=model,
                # Trigger when conversation history reaches 4000 tokens
                trigger=("tokens", 10000),
                # Keep the 20 most recent messages intact after summarizing older ones
                keep=("messages", 20),
            ),
        ],
    )

    input = state['input']
    messages = state.get('messages', [])
    inputMessage = HumanMessage(content=input)

    # 本轮发出去的全部消息（历史 + 本轮用户输入），进 agent 的同时留作后面提取基准。
    input_messages = messages + [inputMessage]

    # 透传父 config（不要自造只带 thread_id 的 config——那样会丢掉回调，子 agent 的
    # 流式事件就回不到外层）。create_agent 默认无 checkpointer，复用父 thread_id 无副作用。
    result = await agent.ainvoke({
        "messages": input_messages
    }, config=config, version="v2")

    # result["messages"] 是「历史 + 本轮」的全量。用 filter_messages(exclude_ids=...) 剔除
    # 输入侧的消息，剩下的就是本轮新增。按下标切不行：SummarizationMiddleware 触发摘要时
    # 前面历史会被换成一条 summary，列表长度和顺序都变了，下标切会把本轮靠前的消息切丢。
    currentRoundMessages = filter_messages(
        result["messages"],
        exclude_ids=[m.id for m in input_messages],
    )

    return {
        "messages": result["messages"],
        # currentRoundMessages 在 State 里挂了 add_messages reducer，这里是追加不是覆盖。
        "currentRoundMessages": currentRoundMessages,
    }

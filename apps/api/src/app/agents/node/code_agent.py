"""codeAgent 节点：按计划读写沙箱内文件。"""

from app.agents.helper.agent_prompt import generate_system_prompt
from app.agents.helper.middleware import TrackingSummarization
from app.agents.node.state import State
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from app.agents.tools import create_tools
from app.agents.tools._common import WORKSPACE
from app.api.sandbox.client.sandbox import get_sandbox_for_id
from app.db.models.session import Role
from app.models.llm import get_model
from langchain.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES


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

    summarization = TrackingSummarization(
        model=model,
        # Trigger when conversation history reaches 10000 tokens
        trigger=("tokens", 10000),
        # Keep the 20 most recent messages intact after summarizing older ones
        keep=("messages", 20),
    )

    agent = create_agent(
        model=model, 
        tools=tools, 
        system_prompt=system_prompt,
        middleware=[summarization],
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

    # 本轮消息（落库 + 前端展示用）从中间件取：它记下了压缩前的完整快照，
    # 详见 TrackingSummarization.current_round_messages。
    currentRoundMessages = summarization.current_round_messages(result["messages"])

    # 外层 messages 走「替换」而不是「追加」。
    #
    # 子 agent 触发压缩时，中间件在**它自己的** add_messages 里把老历史换成
    # [summary, ...最近20条]，那个 RemoveMessage(REMOVE_ALL_MESSAGES) 当次就被消费掉了
    # （reducer 见到它直接 return right[标记之后:]）。所以这里拿到的 result["messages"]
    # 已经不含删除标记，直接返回的话外层会走按 id 合并：老历史 id 都在、一条不删，
    # summary 是新 id 被追加——压缩等于白做，状态反而越滚越大。
    #
    # 这里把删除标记重新带上，让外层的 reducer 也走短路分支，老历史才真正被摘要替换。
    if summarization.triggered:
        messages_update = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *result["messages"]]
    else:
        messages_update = result["messages"]
        
    return {
        "messages": messages_update,
        "currentRoundMessages": currentRoundMessages,
    }

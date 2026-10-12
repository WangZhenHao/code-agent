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

    agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)

    input = state['input']
    message = [item['content'] for item in input if item['type'] == 'text']

    # 透传父 config（不要自造只带 thread_id 的 config——那样会丢掉回调，子 agent 的
    # 流式事件就回不到外层）。create_agent 默认无 checkpointer，复用父 thread_id 无副作用。
    result = await agent.ainvoke({
        "messages": [{"role": Role.user, "content": message[0]}]
    }, config=config)

    print(f"[codeAgent] result: {result}")
    return {"messages": [{"role": "assistant", "content": "[codeAgent] 占位：待接入沙箱工具"}]}

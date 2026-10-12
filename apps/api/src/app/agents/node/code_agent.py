"""codeAgent 节点：按计划读写沙箱内文件。"""

from app.agents.helper.agent_prompt import generate_system_prompt
from app.agents.node.state import State
from langchain.agents import create_agent

from app.agents.tools import create_tools
from app.agents.tools._common import WORKSPACE
from app.api.sandbox.client.sandbox import get_sandbox_for_id
from app.db.models.session import Role
from app.models.llm import get_model


def code_agent(state: State):
    """agent 节点的核心逻辑：按计划读写沙箱内文件。"""

    session_id = state['session']['id']
    sandbox = get_sandbox_for_id(session_id)
    tools = create_tools(sandbox, mode=state['mode'])
    model = get_model(state['model'])
    system_prompt = generate_system_prompt(cwd=WORKSPACE, mode=state['mode'], project_context='')

    agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)
    config = {"configurable": {"thread_id": session_id}}

    input = state['input']
    message = [item['content'] for item in input if item['type'] == 'text']

    result = agent.invoke({
        "messages": [{"role": Role.user, "content": message[0]}]
    }, config=config)

    print(f"[codeAgent] result: {result}")
    return {"messages": [{"role": "assistant", "content": "[codeAgent] 占位：待接入沙箱工具"}]}

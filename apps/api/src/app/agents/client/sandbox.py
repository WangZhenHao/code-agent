from k8s_agent_sandbox import SandboxClient
from k8s_agent_sandbox.models import SandboxLocalTunnelConnectionConfig

# Router 装在本项目的命名空间（见 deploy/api/agent-sandbox-router/），不是上游默认的
# agent-sandbox-system。SDK 会据此 port-forward svc/sandbox-router-svc，对不上就连不上。
#
# server_port 跟随沙箱镜像里官方运行时（uvicorn）的端口，也就是
# deploy/api/sandbox-image/index.yaml 声明的 containerPort: 8888。
# 该值作为 X-Sandbox-Port 头交给 router。
client = SandboxClient(
    connection_config=SandboxLocalTunnelConnectionConfig(
        router_namespace="my-agent-sandbox-system",
        server_port=8888,
    )
)

# create_sandbox 的 namespace 是**沙箱 Pod 所在的命名空间**（不是 router 那个），
# 必须与 deploy/api/sandbox-warmpool/index.yaml 一致 —— 池、模板、claim 三者同命名空间。
sandbox = client.create_sandbox(warmpool="python-sandbox-warmpool", namespace="default")
try:
    print(sandbox.commands.run("echo 'Hello from Local!'").stdout)
finally:
    sandbox.terminate()
"""沙箱客户端单例。

模块级变量，全局共用一份 SandboxClient：它持有到 router 的 port-forward
连接，重复创建会各起一条隧道、白白占资源，所以进程内只建这一个。

注意 SandboxClient() 在构造时就建立连接，所以 import 本模块即产生副作用
（连 router），这正是"单例变量"的代价——想改成懒加载得换回工厂函数。
"""

from k8s_agent_sandbox import SandboxClient
from k8s_agent_sandbox.models import SandboxLocalTunnelConnectionConfig

# Router 装在本项目的命名空间（见 deploy/api/agent-sandbox-router/），不是上游默认的
# agent-sandbox-system。SDK 会据此 port-forward svc/sandbox-router-svc，对不上就连不上。
#
# server_port 跟随沙箱镜像里官方运行时（uvicorn）的端口，也就是
# deploy/api/sandbox-image/index.yaml 声明的 containerPort: 8888。
# 该值作为 X-Sandbox-Port 头交给 router。
ROUTER_NAMESPACE = "my-agent-sandbox-system"
SERVER_PORT = 8888

# create_sandbox 的 namespace 是**沙箱 Pod 所在的命名空间**（不是 router 那个），
# 必须与 deploy/api/sandbox-warmpool/index.yaml 一致 —— 池、模板、claim 三者同命名空间。
SANDBOX_NAMESPACE = "default"
WARMPOOL = "python-sandbox-warmpool"


sandbox_client = SandboxClient(
    connection_config=SandboxLocalTunnelConnectionConfig(
        router_namespace=ROUTER_NAMESPACE,
        server_port=SERVER_PORT,
    )
)

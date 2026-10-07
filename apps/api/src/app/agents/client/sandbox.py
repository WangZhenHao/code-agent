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

# 沙箱里 Next 应用的公网访问域名。这是**部署层约定**，不是 SDK 能告诉你的：
# 通配 Ingress（deploy/api/sandbox-ingress/index.yaml）把 `<沙箱ID>.<域名>` 的
# 子域名剥出来当 X-Sandbox-ID 交给 router，固定转发到沙箱内 3000 端口的 dev server。
# 必须与那条 Ingress 的通配 host 对齐。*.localtest.me 全解析到 127.0.0.1，
# 是本地 Chrome 首选；备用 *.k8s.orb.local 有不可达 IPv6 的坑。
PUBLIC_DOMAIN = "localtest.me"


sandbox_client = SandboxClient(
    connection_config=SandboxLocalTunnelConnectionConfig(
        router_namespace=ROUTER_NAMESPACE,
        server_port=SERVER_PORT,
    )
)


def sandbox_url(sandbox, domain: str = PUBLIC_DOMAIN) -> str:
    """拼沙箱里 Next 应用的公网访问地址。

    用 sandbox_id 而非 claim_name：Ingress 正则从 Host 剥出的子域名要能被 router
    解析回沙箱目标，warmpool 场景下这俩不相等（claim 是新建的，sandbox 名来自池）。
    端口由 Ingress 固定成 3000，所以这里不编码端口。
    """
    return f"http://{sandbox.sandbox_id}.{domain}/"

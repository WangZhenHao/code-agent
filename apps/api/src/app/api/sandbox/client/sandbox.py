"""沙箱客户端单例。

模块级变量，全局共用一份 SandboxClient：它持有到 router 的 port-forward
连接，重复创建会各起一条隧道、白白占资源，所以进程内只建这一个。

注意 SandboxClient() 在构造时就建立连接，所以 import 本模块即产生副作用
（连 router），这正是"单例变量"的代价——想改成懒加载得换回工厂函数。
"""

import logging
import re

from k8s_agent_sandbox import SandboxClient
from k8s_agent_sandbox.constants import (
    SANDBOX_API_GROUP,
    SANDBOX_API_VERSION,
    SANDBOX_PLURAL_NAME,
)
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

# 应用侧给沙箱起的逻辑 ID。SDK 不允许指定沙箱名（claim 名是内部 uuid，sandbox 名
# 在 warmpool 场景下继承自池），所以只好把 ID 贴成 label 当外部索引键：
# create_sandbox_for_id 写它，get_sandbox_for_id 按它查回 claim。
# key 带 "code-agent/" 前缀（合法 DNS 子域），与未来其他组件写入的 label 隔开。
SANDBOX_ID_LABEL = "code-agent/sandbox-id"

# k8s label 值约束：<=63 字符，首尾字母数字，中间只允许 [-A-Za-z0-9_.]。
# 提前本地校验，免得把非法值交给 apiserver 后拿一个难读的 422。
_LABEL_VALUE_RE = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$")


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


def _validate_sandbox_id(sandbox_id: str) -> None:
    if not sandbox_id or len(sandbox_id) > 63 or not _LABEL_VALUE_RE.match(sandbox_id):
        raise ValueError(
            f"非法沙箱 ID {sandbox_id!r}：需 1-63 字符，首尾为字母数字，"
            f"中间只允许 [-A-Za-z0-9_.]（作为 k8s label 值写入）。"
        )


def create_sandbox_for_id(sandbox_id: str, *, ready_timeout: int = 180):
    """用给定的逻辑 ID 创建沙箱，返回沙箱句柄。

    ID 只是贴成 label，不改变沙箱的真实名字（claim/sandbox 名仍由 SDK 生成）。
    同一个 ID 被重复调用会各建一个沙箱、label 相同——create 不做去重，
    要"复用已有"先用 get_sandbox_for_id 探一下。
    """
    _validate_sandbox_id(sandbox_id)
    return sandbox_client.create_sandbox(
        warmpool=WARMPOOL,
        namespace=SANDBOX_NAMESPACE,
        sandbox_ready_timeout=ready_timeout,
        labels={SANDBOX_ID_LABEL: sandbox_id},
    )


def get_sandbox_for_id(sandbox_id: str):
    """按逻辑 ID 找回沙箱句柄；不存在返回 None。

    走 label_selector 列出 claim，get_sandbox 会顺带校验底层 Sandbox 还在、
    不在则抛 SandboxNotFoundError。列出多条（同 ID 建过多次）时取最新一条，
    claim 名后缀是随机 hex 无时序含义，这里只保证"能拿回一个可用句柄"。
    """
    _validate_sandbox_id(sandbox_id)
    claim_names = sandbox_client.list_all_sandboxes(
        namespace=SANDBOX_NAMESPACE,
        label_selector=f"{SANDBOX_ID_LABEL}={sandbox_id}",
    )
    if not claim_names:
        return None
    return sandbox_client.get_sandbox(claim_names[-1], namespace=SANDBOX_NAMESPACE)


# Sandbox CR 的 spec.operatingMode 取值。Running/Suspended 是 CRD schema 里的全部枚举，
# 默认 Running：改回 Running 时控制器按原 podTemplate 重建 Pod 并绑回同一块 PVC。
OPERATING_MODE_RUNNING = "Running"
OPERATING_MODE_SUSPENDED = "Suspended"

logger = logging.getLogger(__name__)


def _get_operating_mode(sandbox) -> str | None:
    """读一次 Sandbox CR，返回当前的 spec.operatingMode；对象已不在返回 None。

    不缓存：暂停/恢复正是这个字段在变，缓存等于把"刚 patch 完"读成旧值。
    """
    obj = sandbox_client.k8s_helper.get_sandbox(sandbox.sandbox_id, SANDBOX_NAMESPACE)
    if not obj:
        return None
    return (obj.get("spec") or {}).get("operatingMode")


def _patch_operating_mode(sandbox, mode: str) -> None:
    """把 Sandbox CR 的 spec.operatingMode 设成 Running / Suspended（merge patch）。

    用 sandbox_id 而非 claim_name 定位：warmpool 场景下 claim 是新建的、Sandbox 名
    继承自池，两者不等（sandbox_url 里同样的理由）。
    """
    sandbox_client.k8s_helper.custom_objects_api.patch_namespaced_custom_object(
        group=SANDBOX_API_GROUP,
        version=SANDBOX_API_VERSION,
        namespace=SANDBOX_NAMESPACE,
        plural=SANDBOX_PLURAL_NAME,
        name=sandbox.sandbox_id,
        body={"spec": {"operatingMode": mode}},
    )


def suspend_sandbox(sandbox) -> None:
    """暂停沙箱：删 Pod、保留 Sandbox CR / Service / PVC，下次回来数据还在。

    与 delete_sandbox 的区别是「可逆」——后者删的是 SandboxClaim，claim 一没
    Sandbox 和卷都跟着走，那是销毁。

    先 close_connection 再 patch，顺序不能反：close_connection 会把 _pod_name 缓存
    清掉（sandbox.py 里就是为 suspend/resume 留的），否则恢复后 port-forward 会指向
    已经不存在的旧 Pod。它只关本地隧道，不动远端。
    """
    sandbox.close_connection()
    _patch_operating_mode(sandbox, OPERATING_MODE_SUSPENDED)


def resume_sandbox(sandbox, *, ready_timeout: int = 180) -> bool:
    """把暂停中的沙箱唤回 Running，阻塞等 Pod 就绪。返回是否真的做了恢复。

    幂等：已在 Running（或 CR 已不在）时直接返回 False，不发 patch、不等 ready。
    等 Pod 就绪是必须的——patch 返回只代表 spec 被受理，调用方拿到句柄立刻
    commands.run 会打在还没起来的 Pod 上。

    注意返回 True 时句柄的 pod IP 是新的：Sandbox.get_pod_ip 每次都现查（不缓存），
    所以同一个句柄对象恢复后仍可用，不必重新 get_sandbox_for_id。
    """
    if _get_operating_mode(sandbox) != OPERATING_MODE_SUSPENDED:
        return False

    logger.info("沙箱处于暂停态，恢复中 sandbox_id=%s", sandbox.sandbox_id)
    _patch_operating_mode(sandbox, OPERATING_MODE_RUNNING)
    sandbox_client.k8s_helper.wait_for_sandbox_ready(
        sandbox.sandbox_id, SANDBOX_NAMESPACE, ready_timeout
    )
    return True


def delete_sandbox(sandbox) -> None:
    """销毁沙箱：删 SandboxClaim，连 PVC 一起释放，**不可逆**。

    与 suspend_sandbox 是"要这份数据"的分水岭，不是两种关闭方式：
    suspend 保留 CR / Service / PVC，下次 resume 能原样回来；delete 把 claim 删掉，
    claim 一没 Sandbox 与卷都跟着走（shutdownPolicy 默认 Delete）。

    误用代价是数据不可逆丢失，所以调用点应当明确是「确定不再需要」的场景
    （用户删会话等），不要拿它替代暂停。

    delete_sandbox 内部会 terminate 句柄并摘掉客户端里的追踪记录；
    namespace 必须与建沙箱时一致（默认 default）。
    """
    sandbox_client.delete_sandbox(sandbox.claim_name, SANDBOX_NAMESPACE)

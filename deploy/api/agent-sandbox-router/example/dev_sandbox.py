"""起一个沙箱、拉起 Next dev server、打印可访问 URL，然后挂住等 Ctrl-C。

用法（在 apps/api 下）：

    uv run python scripts/dev_sandbox.py

Ctrl-C 结束时自动 `terminate()` 回收沙箱。
"""
from __future__ import annotations

import signal
import sys
import time

from k8s_agent_sandbox import SandboxClient
from k8s_agent_sandbox.models import SandboxLocalTunnelConnectionConfig

# Router 装在本项目命名空间（见 deploy/api/agent-sandbox-router/）。
# server_port 是沙箱内官方运行时的端口（deploy/api/sandbox-image/index.yaml）。
ROUTER_NAMESPACE = "my-agent-sandbox-system"
SERVER_PORT = 8888
WARMPOOL = "python-sandbox-warmpool"
SANDBOX_NAMESPACE = "default"

# 沙箱内 Next dev server 的端口与外网可访问域名（见 deploy/api/sandbox-ingress/）。
DEV_PORT = 3000
# localtest.me 的所有子域名解析到 127.0.0.1（含正常回环 IPv6 ::1），
# 绕开 k8s.orb.local 那个不可达 IPv6 与代理 fake-ip 冲突的坑。
PUBLIC_DOMAIN = "localtest.me"


def main() -> int:
    client = SandboxClient(
        connection_config=SandboxLocalTunnelConnectionConfig(
            router_namespace=ROUTER_NAMESPACE,
            server_port=SERVER_PORT,
        )
    )

    print("→ 创建沙箱…", flush=True)
    sandbox = client.create_sandbox(warmpool=WARMPOOL, namespace=SANDBOX_NAMESPACE)
    sid = sandbox.sandbox_id

    # 确保退出时回收，不然沙箱会一直占着资源。
    def _cleanup(*_: object) -> None:
        print("\n→ 回收沙箱…", flush=True)
        try:
            sandbox.terminate()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    try:
        # 后台起 dev server。运行时 /execute 用 shlex.split 不经 shell，
        # 所以显式 `sh -c`，末尾 `&` 让 shell 立刻返回、不阻塞到超时。
        print("→ 启动 Next dev server…", flush=True)
        sandbox.commands.run(
            "sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'"
        )

        # 等它就绪。首次启动要编译，通常十几秒。
        print("→ 等待 dev server 就绪…", flush=True)
        ready = False
        probe = (
            f"sh -c 'curl -s -o /dev/null -w %{{http_code}} localhost:{DEV_PORT}/ 2>/dev/null'"
        )
        for _ in range(40):
            time.sleep(3)
            code = (sandbox.commands.run(probe).stdout or "").strip()
            if code == "200":
                ready = True
                break

        url = f"http://{sid}.{PUBLIC_DOMAIN}/"
        print()
        if ready:
            print(f"✅ 就绪：{url}", flush=True)
        else:
            print(f"⚠️  dev server 未在预期时间内就绪，仍给出地址：{url}", flush=True)
            print("   排查：kubectl -n default exec " + sid + " -c sandbox -- cat /tmp/next.log")
        print()
        print("   （Ctrl-C 结束并回收沙箱）", flush=True)

        # 挂住，直到 Ctrl-C。
        while True:
            time.sleep(3600)
    finally:
        pass


if __name__ == "__main__":
    raise SystemExit(main())

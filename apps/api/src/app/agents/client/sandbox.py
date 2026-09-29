from k8s_agent_sandbox import SandboxClient
from k8s_agent_sandbox.models import SandboxLocalTunnelConnectionConfig

# Router deployed in the default agent-sandbox-system namespace:
client = SandboxClient(
    connection_config=SandboxLocalTunnelConnectionConfig()
)

# If the router is deployed in a different namespace (e.g. "default"):
# client = SandboxClient(
#     connection_config=SandboxLocalTunnelConnectionConfig(router_namespace="default")
# )

sandbox = client.create_sandbox(warmpool="python-sandbox-warmpool", namespace="default")
try:
    print(sandbox.commands.run("echo 'Hello from Local!'").stdout)
finally:
    sandbox.terminate()
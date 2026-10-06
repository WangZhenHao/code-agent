# 沙箱镜像：官方运行时（自带 /execute + 文件 API）+ Node 24 + Next 模板。
#
# 构建上下文是**仓库根**，不是模板目录：
#
#   docker build -f deploy/api/sandbox-image/Dockerfile \
#     -t code-agent/sandbox-base:latest .
#
# 为什么要从官方运行时派生：agent-sandbox 的编排器（sandbox-with-extensions.yaml）
# 只管 Pod 生命周期，**不执行命令**。SDK 的 commands.run 走 `POST /execute`，这个端点
# 必须由【镜像里的运行时】提供。官方 quickstart 的模板指向
# python-runtime-sandbox 镜像，它自带 FastAPI 运行时 —— 照着抄这个姿势即可，
# 不用自己写。派生 = 继承它的 /execute、/upload、/download、/list、/exists，
# 再叠上我们的 Node 与模板。
#
# 已知限制：官方运行时的 /execute 用 shlex.split 拆参数、**不经 shell**，
# 所以 `npm run dev` 可以，`npm install && npm run dev` 不行。

# python:3.14-slim 基座，自带 main.py + uvicorn，监听 8888。
FROM us-central1-docker.pkg.dev/k8s-staging-images/agent-sandbox/python-runtime-sandbox:latest-main

USER root

# Node 24 走 nodesource（base 的 debian 自带的 nodejs 太旧）。ripgrep / git 是
# 沙箱里做代码检索与版本操作的合理预置。build-essential 给 node-gyp 兜底
# （sharp 这类原生依赖没有预编译包时要用）。
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      git \
      ripgrep \
      build-essential \
      python3 \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# 模板进 /workspace，归 1000（官方运行时的容器用户）。
# 目标目录由 COPY 创建并随 --chown 归 1000，不存在「已存在目录属主不动」那个坑
# （那是之前 WORKDIR + --chown 组合踩过的，这里没有 WORKDIR 预建目录）。
COPY --chown=1000:1000 templete/nextjs/file/ /workspace/

# 官方运行时镜像里 uid 1000 没有 passwd 条目，HOME 默认是 /，npm 会去写 /.npm 然后
# EACCES（「cache folder contains root-owned files」）。给它一个真正的 home。
RUN mkdir -p /home/node && chown -R 1000:0 /home/node

# 以 1000 装依赖，node_modules 与 npm 缓存自然归它所有，不用事后 chown -R
# （后者会在层里复制一份完整的 node_modules，~500MB）。npm ci 严格按 lockfile
# 还原，package.json 与锁文件不一致会直接失败 —— 这是构建可复现性的来源。
USER 1000
ENV HOME=/home/node
RUN cd /workspace \
 && npm ci --no-audit --no-fund \
 && rm -rf "${HOME}/.npm/_cacache"

# 官方运行时 get_base_dir() 读这个：/execute 的 cwd 与文件 API 的根都指向 /workspace。
ENV SANDBOX_BASE_DIR=/workspace

# 刻意不覆盖 CMD/ENTRYPOINT —— 继承官方那条 `uvicorn main:app --host 0.0.0.0 --port 8888`，
# 它就是 /execute 服务本身。

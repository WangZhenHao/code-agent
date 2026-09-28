# 沙箱基础镜像：Next.js 模板 + 预装依赖 + 可重启的 dev server 入口。
#
# 构建上下文是**仓库根**，不是模板目录：
#
#   docker build -f deploy/api/sandbox-image/Dockerfile \
#     -t code-agent/sandbox-base:latest .
#
# 为什么是仓库根：入口脚本 entrypoint.sh 跟本 Dockerfile 同目录，构建上下文若只给
# 模板目录就 COPY 不到它。而 entrypoint.sh 不能放进模板里 —— templete/nextjs/file
# 是个 gitlink 子模块（独立仓库、独立历史），放进去等于让它变成沙箱工作区的一部分，
# agent 一次 rm 就把容器的重启逻辑删了。所以脚本走仓库根上下文，另配根目录的
# .dockerignore 白名单，只放行模板与本脚本。
#
# 依赖用 npm ci 装，依据模板里已有的 package-lock.json —— 换 pnpm 得先生成
# pnpm-lock.yaml，而模板现在只带了 npm 的锁文件。
#
# 镜像以非 root 的 node 用户运行（uid 1000），agent 在沙箱内写的文件天然归它所有。

# Node 24 配 Next 16 刚好；slim 变体省掉一堆用不上的用户态工具，需要什么自己 apt 装。
FROM node:24-bookworm-slim

# --no-install-recommends：slim 镜像的本意就是小，别被 recommends 拖回来。
# build-essential / python3 给 node-gyp 兜底（sharp 这类原生依赖的预编译包没命中时要用）。
# ripgrep 模板里没有，但 agent 在沙箱内搜代码靠它，属沙箱的合理预置。
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      unzip \
      git \
      ripgrep \
      procps \
      util-linux \
      python3 \
      build-essential \
      dumb-init \
 && rm -rf /var/lib/apt/lists/*

# 沙箱工作区。会话内的代码读写都在这里，与镜像里预置的模板同路径。
WORKDIR /workspace

# 入口脚本先就位，放 /usr/local/bin 而不是 /workspace ——
# /workspace 可能被持久卷整个盖住，脚本被盖掉容器就起不来了。
# 单独一层、在 COPY 模板之前，模板改动能命中后面的层缓存。
COPY deploy/api/sandbox-image/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# --chown 让 /workspace 直接归 node 所有。相比装完再 chown -R 更好：后者会在层里
# 复制一份完整的 node_modules（~500MB），前者只在 COPY 时定一次属主。
# --chown 顺带挡住模板子模块 .git 的属主问题（.dockerignore 已把它排除）。
COPY --chown=node:node templete/nextjs/file/ /workspace/

# 以 node 身份装依赖，node_modules 与 npm 缓存自然归它所有，不需要事后改权限。
# npm ci 严格按 lockfile 还原，package.json 与锁文件不一致会直接失败 —— 这正是
# 构建可复现性的来源，不要换成 npm install。
USER node
RUN npm ci --no-audit --no-fund \
 && rm -rf "${HOME}/.npm/_cacache"

# Next dev server。bind 到 0.0.0.0 才能在 Pod 外访问；watchpack 走轮询，
# 否则挂载卷上的文件变更触发不了 HMR。
ENV NODE_ENV=development \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    WATCHPACK_POLLING=true \
    NEXT_TELEMETRY_DISABLED=1

# 3000 是 Next 的默认端口（原文件里的 8080/9090 是 agent-sandbox 控制器的指标端口，
# 与沙箱无关）。8090 留给沙箱自带的辅助进程。
EXPOSE 3000

# dumb-init 当 PID 1 收信号。沙箱销毁时 Next dev 会拉起一整个进程树，
# 没有 init 的话 SIGTERM 到不了子进程，容器要等满 30s 才被 SIGKILL。
# dumb-init 之后跑 entrypoint.sh，由它负责 dev server 的「退出即重启」。
ENTRYPOINT ["dumb-init", "--"]
CMD ["/usr/local/bin/entrypoint.sh"]

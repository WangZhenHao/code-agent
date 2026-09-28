#!/usr/bin/env bash
# 沙箱容器的 PID 1 逻辑（外层还有 dumb-init 收信号、当真正的 init）。
#
# 只做一件事：把 Next dev server 拉起来，并且在它退出后不断重启。
# agent 在沙箱里改代码会让 dev server 崩，但**会话不该跟着崩** —— 容器一退，
# 上层 Sandbox 就被回收，agent 手上的 handle 全废。所以 dev server 是「可重启的
# 子进程」，容器的存活由这一层保证。
#
# 不做的事：不重启 sandboxd、不装依赖做「一次性的启动准备」。前者本镜像里没有这个
# 二进制；后者的产物（node_modules）在镜像构建时就已经固化，见 Dockerfile。
set -u

# /workspace 常被挂成持久卷（会话间复用 node_modules / .next，省掉几分钟冷启动）。
# 卷会盖掉镜像里同路径的内容 —— 所以这个脚本自己不放在 /workspace 下，放 /usr/local/bin。
WORKDIR=/workspace

# 收到 SIGTERM 就退出 wait，让容器尽快结束。
# 真正的清理交给 dumb-init：这一层只是 bash 脚本，两个后台循环是它的子进程，
# bash 默认不转发 SIGTERM，靠 pkill 补一刀，再不行就等运行时 SIGKILL。
trap 'pkill -P $$ 2>/dev/null; exit 0' TERM INT

cd "$WORKDIR" || exit 1

while true; do
  # 卷刚挂上时工作区可能是空的，等模板/代码就位再起。缺了这层，
  # npm run dev 每次都会立刻报错退出，循环变成空转刷屏。
  if [ -f package.json ]; then

    # dev server 崩过会留 core dump（Next 在 OOM / 原生模块出错时尤其容易），
    # 几百 MB 一个，攒几个就把卷撑死。重启前先清掉。
    rm -f core

    # 装了依赖就不动它 —— 每次重启都 npm ci 会让重启从「秒级」变成「分钟级」。
    # 只有 node_modules 缺了（新卷、被 agent 删了）才补装。
    if [ ! -d node_modules ]; then
      # npm install（而非 ci）：package.json 与锁文件不一致时 ci 会直接失败，
      # 而 agent 新增依赖后两者本来就是不一致的 —— 这里要的是「能跑起来」，
      # 不是「严格可复现」。镜像构建那一步用的是 ci，可复现性由构建保证。
      npm install --no-audit --no-fund || {
        echo "npm install 失败，3s 后重试" >&2
        sleep 3
        continue
      }
    fi

    # exec 让 npm 顶掉当前子 shell，SIGTERM 直达 next 进程，不用多一层转发。
    # 不加 exec，多出来的 shell 会吞掉信号，容器要多等一轮才关掉。
    npm run dev
    echo "dev server 退出（code=$?），2s 后重启" >&2
  fi

  sleep 2
done &

# 保住 PID 1：这个脚本一退出容器就结束。
# 上面那个循环是唯一的「服务」，但用 wait 而不是在前台直接跑它，
# 是为了留住 trap 的处理时机 —— bash 在等 wait 时才会响应信号。
wait

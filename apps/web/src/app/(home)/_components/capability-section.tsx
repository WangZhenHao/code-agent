import Image from "next/image"

const CAPABILITIES = [
  {
    image: "/home/1.png",
    title: "Agent 友好的云端沙箱环境",
    description:
      "专为 AI Agent 打造的云端开发环境，内置文件系统、终端与预览工具，不再担心本地环境损坏和文件丢失，完全为 AI Agent 设计的开发环境。",
  },
  {
    image: "/home/2.png",
    title: "开发所需的集成资源，一应俱全",
    description:
      "数据库、对象存储、AI 模型、联网检索、文件处理等服务集成，全部由平台提供，无需到处寻找集成服务，一站式完成开发。",
  },
  {
    image: "/home/3.png",
    title: "便捷的部署服务，让你的产品更快见到用户",
    description:
      "域名、云服务器、SSL 证书等部署链路一键打通。产物上线后由平台提供版本管理、运行监控与持续运维。",
  },
]

export function CapabilitySection() {
  return (
    <section className="mt-24 w-full max-w-350">
      <p className="text-sm text-muted-foreground">核心能力</p>
      <h2 className="mt-6 max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
        从需求到上线，你所需要的，一应俱全
      </h2>
      <p className="mt-6 max-w-3xl text-base text-muted-foreground">
        领先的云端开发环境搭配全栈集成资源与一键部署，让开发者专注于业务创造而非基础设施搭建。
      </p>

      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CAPABILITIES.map((item) => (
          <div
            key={item.title}
            className="flex flex-col rounded-2xl bg-[#F1F0ED] p-1.5"
          >
            <div className="relative aspect-[8/5] w-full overflow-hidden rounded-xl">
              <Image
                src={item.image}
                alt={item.title}
                fill
                sizes="(min-width: 1024px) 440px, (min-width: 640px) 50vw, 100vw"
                className="object-cover"
              />
            </div>
            <div className="px-4 pt-5 pb-6">
              <h3 className="text-lg font-semibold tracking-tight">
                {item.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {item.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

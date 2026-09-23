import { Layout } from 'antd'
import { useState } from 'react'

import HeaderBar from './HeaderBar'
import SideNav from './SideNav'

const { Content, Sider } = Layout

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <Layout className="min-h-full">
      <Sider
        theme="light"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        width={220}
        className="border-r border-gray-200"
        // Sider 内层容器是 position:sticky，必须给足高度，否则菜单下面会漏出页面底色
        style={{ background: '#fff' }}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-14 shrink-0 items-center gap-2 px-4">
            <div className="size-6 shrink-0 rounded-md bg-brand-500" />
            {!collapsed && (
              <span className="truncate text-sm font-semibold text-gray-900">
                code-agent
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <SideNav />
          </div>
        </div>
      </Sider>

      <Layout className="min-w-0">
        <HeaderBar />
        <Content className="overflow-auto p-6">
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500">
            <p className="text-base font-medium text-gray-700">
              管理台骨架已就绪
            </p>
            <p className="mt-2 text-sm">
              antd 6 + Tailwind CSS 4 + React 19 + Vite。下一步在
              <span className="mono mx-1">src/pages/</span>
              下添加页面并接入路由。
            </p>
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

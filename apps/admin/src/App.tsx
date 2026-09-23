import { App as AntdApp, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'dayjs/locale/zh-cn'

import AdminLayout from './layout/AdminLayout'

/**
 * 全局 Provider。antd 的 theme token 和 Tailwind 的 @theme 是两套体系，
 * 这里只把主色对齐，颜色以 antd token 为准（组件内部由 antd 控制）。
 */
export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#2f6bff',
          borderRadius: 8,
          fontSize: 14,
        },
      }}
    >
      <AntdApp>
        <AdminLayout />
      </AntdApp>
    </ConfigProvider>
  )
}

import {
  DashboardOutlined,
  DeploymentUnitOutlined,
  MessageOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Menu } from 'antd'

const items = [
  { key: 'overview', icon: <DashboardOutlined />, label: '总览' },
  { key: 'sessions', icon: <MessageOutlined />, label: '会话' },
  { key: 'sandboxes', icon: <DeploymentUnitOutlined />, label: '沙箱' },
  { key: 'settings', icon: <SettingOutlined />, label: '设置' },
]

export default function SideNav() {
  return (
    <Menu
      mode="inline"
      defaultSelectedKeys={['overview']}
      items={items}
      style={{ borderInlineEnd: 'none' }}
    />
  )
}

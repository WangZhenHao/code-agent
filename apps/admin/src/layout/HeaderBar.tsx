import { BellOutlined, ReloadOutlined } from '@ant-design/icons'
import { Avatar, Badge, Button, Space, Tag, Tooltip } from 'antd'

/**
 * 用普通 div 而不是 antd 的 Layout.Header：
 * Header 自带深色背景且优先级高于 Tailwind 的 bg-white，会压掉样式。
 */
export default function HeaderBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <span className="text-base font-medium text-gray-900">管理台</span>
        <Tag color="green" bordered={false} className="m-0">
          dev
        </Tag>
      </div>

      <Space size="middle">
        <Tooltip title="重新拉取数据">
          <Button type="text" icon={<ReloadOutlined />} />
        </Tooltip>
        <Badge dot>
          <Button type="text" icon={<BellOutlined />} />
        </Badge>
        <Avatar size="small" style={{ backgroundColor: '#2f6bff' }}>
          A
        </Avatar>
      </Space>
    </header>
  )
}

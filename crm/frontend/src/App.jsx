import { useState, useEffect } from 'react'
import {
  Layout, Typography, Card, Row, Col, Statistic, Table, Tag, Button,
  Drawer, Descriptions, Timeline, Select, Input, Space, message, Tabs,
  Progress, Empty, Spin, Badge, Modal, Form
} from 'antd'
import {
  DashboardOutlined, DatabaseOutlined, BellOutlined,
  CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined,
  SendOutlined, UserOutlined, GlobalOutlined, FilterOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from './api'

const { Title, Text } = Typography
const { TabPane } = Tabs

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusTag({ status }) {
  const map = {
    NEW:        { color: 'default',  icon: <ClockCircleOutlined /> },
    REVIEWED:   { color: 'processing', icon: <ClockCircleOutlined /> },
    QUALIFIED:  { color: 'blue',    icon: <CheckCircleOutlined /> },
    SENT:       { color: 'purple',  icon: <SendOutlined /> },
    CONTACTED:  { color: 'cyan',    icon: <UserOutlined /> },
    CONVERTED:  { color: 'success', icon: <CheckCircleOutlined /> },
    LOST:       { color: 'error',   icon: <DeleteOutlined /> },
  }
  const cfg = map[status] || { color: 'default' }
  return (
    <Tag color={cfg.color} icon={cfg.icon} style={{ borderRadius: 12 }}>
      {status}
    </Tag>
  )
}

function LeadTypeTag({ type }) {
  const map = { VALID: 'success', INVALID: 'error', FOLLOW_UP: 'warning' }
  return <Tag color={map[type] || 'default'}>{type || '—'}</Tag>
}

function ScoreBadge({ score }) {
  if (!score) return <Text type="secondary">—</Text>
  const pct = score * 20
  const color = score >= 4 ? '#52c41a' : score >= 3 ? '#faad14' : '#ff4d4f'
  return <Progress percent={pct} size="small" steps={5} strokeColor={color} style={{ width: 70 }} />
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

function Dashboard({ clientId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.dashboardSummary(clientId)
      setData(res)
    } catch (e) {
      message.error('Failed to load dashboard: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [clientId])

  if (loading) return <Spin style={{ display: 'block', margin: 60 }} />

  const { summary, source_breakdown } = data || {}

  return (
    <div style={{ padding: '0 8px' }}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { label: 'Total Leads', value: summary?.total_leads ?? 0, color: '#1677ff' },
          { label: 'Qualified', value: summary?.qualified_leads ?? 0, suffix: <Text type="secondary">({summary?.qualification_rate ?? 0}%)</Text> },
          { label: 'Sent to Client', value: summary?.sent_to_client ?? 0 },
          { label: 'Converted', value: summary?.converted ?? 0, color: '#52c41a' },
          { label: 'Lost', value: summary?.lost ?? 0, color: '#ff4d4f' },
          { label: 'Conversion Rate', value: `${summary?.conversion_rate ?? 0}%`, color: '#722ed1' },
        ].map((s, i) => (
          <Col xs={12} sm={8} md={4} key={i}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Statistic
                title={<Text type="secondary" style={{ fontSize: 12 }}>{s.label}</Text>}
                value={s.value}
                valueStyle={{ color: s.color || undefined, fontSize: 22 }}
                suffix={s.suffix}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {summary?.avg_response_time_hours != null && (
        <Card size="small" style={{ marginBottom: 24 }}>
          <Text type="secondary">
            Avg. response time (NEW → sent to client):{' '}
            <Text strong>{summary.avg_response_time_hours}h</Text>
          </Text>
        </Card>
      )}

      {source_breakdown?.length > 0 && (
        <Card title="Qualified Leads by Source" size="small">
          {source_breakdown.map(src => {
            const rate = src.count > 0 ? Math.round(src.qualified_count / src.count * 100) : 0
            return (
              <div key={src.source} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <Tag style={{ minWidth: 120 }}>{src.source.replace('_', ' ')}</Tag>
                <Progress
                  percent={rate}
                  size="small"
                  format={p => `${p}% (${src.qualified_count}/${src.count})`}
                  style={{ flex: 1 }}
                />
              </div>
            )
          })}
        </Card>
      )}
    </div>
  )
}

// ── Leads ───────────────────────────────────────────────────────────────────────

const STATUS_OPTIONS = ['NEW','REVIEWED','QUALIFIED','SENT','CONTACTED','CONVERTED','LOST']
const SOURCE_OPTIONS  = ['HARO','CONNECTIVELY','GUEST_OUTREACH','WEB_SEARCH','MANUAL']
const TYPE_OPTIONS    = ['VALID','INVALID','FOLLOW_UP']

export function LeadsTab({ clientId, refreshKey }) {
  const [leads, setLeads] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({})
  const [search, setSearch] = useState('')
  const [selectedRow, setSelectedRow] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [updating, setUpdating] = useState(false)

  const loadLeads = async () => {
    setLoading(true)
    try {
      const params = { client_id: clientId, limit: pageSize, offset: (page - 1) * pageSize }
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      if (filters.lead_type) params.lead_type = filters.lead_type
      if (search) params.search = search
      const res = await api.listLeads(params)
      setLeads(res.leads)
      setTotal(res.total)
    } catch (e) {
      message.error('Failed to load leads')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadLeads() }, [page, pageSize, filters, search, refreshKey, clientId])

  const columns = [
    {
      title: 'Date',
      dataIndex: 'created_at',
      render: d => dayjs(d).format('MMM D, YYYY'),
      width: 110,
    },
    {
      title: 'Company',
      dataIndex: 'company_name',
      render: (v, r) => (
        <div>
          <Text strong>{v || '—'}</Text>
          {r.contact_name && <br />}
          {r.contact_name && <Text type="secondary" style={{ fontSize: 12 }}>{r.contact_name}</Text>}
        </div>
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      render: s => <Tag>{s?.replace('_', ' ')}</Tag>,
      width: 130,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      render: s => <StatusTag status={s} />,
      width: 140,
    },
    {
      title: 'Type',
      dataIndex: 'lead_type',
      render: t => <LeadTypeTag type={t} />,
      width: 100,
    },
    {
      title: 'Score',
      dataIndex: 'quality_score',
      render: s => <ScoreBadge score={s} />,
      width: 90,
    },
    {
      title: 'Contact',
      dataIndex: 'contact_email',
      render: e => e ? <Text style={{ fontSize: 12 }} copyable={{ text: e }}>{e}</Text> : '—',
    },
    {
      title: '',
      render: (_, r) => (
        <Button size="small" onClick={() => { setSelectedRow(r); setDrawerOpen(true) }}>
          View
        </Button>
      ),
      width: 70,
    },
  ]

  return (
    <div>
      {/* Filter bar */}
      <Space wrap style={{ marginBottom: 12 }}>
        <Input.Search
          placeholder="Search company / email / name"
          style={{ width: 240 }}
          onSearch={v => { setSearch(v); setPage(1) }}
          allowClear
        />
        <Select allowClear placeholder="Status" style={{ width: 130 }}
          onChange={v => { setFilters(f => ({ ...f, status: v })); setPage(1) }}>
          {STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
        </Select>
        <Select allowClear placeholder="Source" style={{ width: 150 }}
          onChange={v => { setFilters(f => ({ ...f, source: v })); setPage(1) }}>
          {SOURCE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s.replace('_',' ')}</Select.Option>)}
        </Select>
        <Select allowClear placeholder="Type" style={{ width: 120 }}
          onChange={v => { setFilters(f => ({ ...f, lead_type: v })); setPage(1) }}>
          {TYPE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
        </Select>
        <Button onClick={() => setFilters({})} size="small">
          <FilterOutlined /> Clear
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>{total} leads</Text>
      </Space>

      <Table
        dataSource={leads}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page, pageSize,
          total, onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          showSizeChanger: true,
          showTotal: t => `${t} leads`,
        }}
        size="small"
        scroll={{ x: 900 }}
      />

      {/* Lead detail drawer */}
      <LeadDrawer
        lead={selectedRow}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setSelectedRow(null) }}
        onUpdate={loadLeads}
      />
    </div>
  )
}

// ── Lead Drawer ────────────────────────────────────────────────────────────────

function LeadDrawer({ lead, open, onClose, onUpdate }) {
  const [notes, setNotes] = useState('')
  const [clientResponse, setClientResponse] = useState('')
  const [status, setStatus] = useState(null)
  const [leadType, setLeadType] = useState(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    if (lead) {
      setNotes(lead.notes || '')
      setClientResponse(lead.client_response || '')
      setStatus(lead.status)
      setLeadType(lead.lead_type)
    }
  }, [lead])

  const handleSave = async () => {
    if (!lead) return
    setSaving(true)
    try {
      await api.updateLead(lead.id, {
        notes,
        client_response: clientResponse,
        status,
        lead_type: leadType,
        conversion_status: status === 'CONVERTED' ? 'CONVERTED' : status === 'LOST' ? 'LOST' : undefined,
      })
      message.success('Lead updated')
      onUpdate()
      onClose()
    } catch (e) {
      message.error('Update failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!lead) return null

  return (
    <Drawer
      title={<Text strong>Lead Details</Text>}
      placement="right"
      width={520}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" loading={saving} onClick={handleSave}>
            Save Changes
          </Button>
        </Space>
      }
    >
      <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Company">{lead.company_name || '—'}</Descriptions.Item>
        <Descriptions.Item label="Contact">{lead.contact_name || '—'}</Descriptions.Item>
        <Descriptions.Item label="Email">{lead.contact_email || '—'}</Descriptions.Item>
        <Descriptions.Item label="Phone">{lead.contact_phone || '—'}</Descriptions.Item>
        <Descriptions.Item label="Website">
          {lead.company_website
            ? <a href={lead.company_website} target="_blank" rel="noreferrer">{lead.company_website}</a>
            : '—'}
        </Descriptions.Item>
        <Descriptions.Item label="Source">{lead.source}</Descriptions.Item>
        {lead.source_query && <Descriptions.Item label="Query">{lead.source_query}</Descriptions.Item>}
        <Descriptions.Item label="Created">{dayjs(lead.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
        {lead.sent_to_client_at && (
          <Descriptions.Item label="Sent to Client">
            {dayjs(lead.sent_to_client_at).format('YYYY-MM-DD HH:mm')}
          </Descriptions.Item>
        )}
      </Descriptions>

      <Form layout="vertical" form={form}>
        <Form.Item label="Status">
          <Select value={status} onChange={setStatus} style={{ width: '100%' }}>
            {STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
          </Select>
        </Form.Item>
        <Form.Item label="Lead Type">
          <Select value={leadType} onChange={setLeadType} allowClear style={{ width: '100%' }}>
            {TYPE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
          </Select>
        </Form.Item>
        <Form.Item label="Quality Score">
          <ScoreBadge score={lead.quality_score} />
          {lead.quality_score && <Text type="secondary" style={{ marginLeft: 8 }}>/5</Text>}
        </Form.Item>

        {lead.message_excerpt && (
          <Form.Item label="Lead Message / Context">
            <div style={{
              background: '#f5f5f5', padding: 12, borderRadius: 6,
              fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto'
            }}>
              {lead.message_excerpt}
            </div>
          </Form.Item>
        )}

        {lead.pitch_sent && (
          <Form.Item label="Pitch Sent">
            <div style={{
              background: '#f0f7ff', padding: 12, borderRadius: 6,
              fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto'
            }}>
              {lead.pitch_sent}
            </div>
          </Form.Item>
        )}

        <Form.Item label="Client Response">
          <Input.TextArea
            value={clientResponse}
            onChange={e => setClientResponse(e.target.value)}
            rows={3}
            placeholder="Notes from the client about this lead..."
          />
        </Form.Item>
        <Form.Item label="Internal Notes">
          <Input.TextArea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={3}
            placeholder="Private notes about this lead..."
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

// ── Main App ───────────────────────────────────────────────────────────────────

export default function App() {
  const [clients, setClients] = useState([])
  const [selectedClientId, setSelectedClientId] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    api.listClients().then(cs => {
      setClients(cs)
      if (cs.length > 0 && !selectedClientId) {
        setSelectedClientId(cs[0].id)
      }
    }).catch(() => {
      message.error('Cannot connect to CRM backend. Is it running?')
    })
  }, [])

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      <Layout.Header style={{ background: '#001529', display: 'flex', alignItems: 'center', gap: 16, padding: '0 24px' }}>
        <Title level={4} style={{ color: '#fff', margin: 0 }}>
          RankBuilder CRM
        </Title>
        {clients.length > 0 && (
          <Select
            value={selectedClientId}
            onChange={id => { setSelectedClientId(id); setRefreshKey(k => k + 1) }}
            style={{ width: 220 }}
            placeholder="Select client"
          >
            {clients.map(c => (
              <Select.Option key={c.id} value={c.id}>{c.company_name}</Select.Option>
            ))}
          </Select>
        )}
        <div style={{ flex: 1 }} />
        <Badge status={clients.length > 0 ? 'success' : 'error'} text={
          <Text style={{ color: '#fff', fontSize: 12 }}>{clients.length > 0 ? `${clients.length} client(s)` : 'No clients'}</Text>
        } />
      </Layout.Header>

      <Layout.Content style={{ padding: '16px 24px' }}>
        {selectedClientId ? (
          <Tabs activeKey={tab} onChange={setTab}>
            <TabPane tab={<span><DashboardOutlined /> Dashboard</span>} key="dashboard">
              <div style={{ background: '#fff', borderRadius: 8, padding: 16 }}>
                <Dashboard clientId={selectedClientId} key={`dash-${selectedClientId}-${refreshKey}`} />
              </div>
            </TabPane>
            <TabPane tab={<span><DatabaseOutlined /> Leads</span>} key="leads">
              <div style={{ background: '#fff', borderRadius: 8, padding: 16 }}>
                <LeadsTab
                  clientId={selectedClientId}
                  refreshKey={refreshKey}
                />
              </div>
            </TabPane>
          </Tabs>
        ) : (
          <Empty description="No clients yet. Run the seed script to create HOS." style={{ marginTop: 80 }}>
            <pre style={{ textAlign: 'left', background: '#f5f5f5', padding: 16, borderRadius: 8 }}>
              # In the crm/backend directory:
              python -m seed
            </pre>
          </Empty>
        )}
      </Layout.Content>
    </Layout>
  )
}

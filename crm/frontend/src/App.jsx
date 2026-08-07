import { useState, useEffect, useRef } from 'react'
import {
  Layout, Typography, Card, Row, Col, Statistic, Table, Tag, Button,
  Drawer, Descriptions, Timeline, Select, Input, Space, message, Tabs,
  Progress, Empty, Spin, Badge, Modal, Form, Divider, Segmented, Rate
} from 'antd'
import {
  DashboardOutlined, DatabaseOutlined, UserOutlined, LogoutOutlined,
  CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined,
  SendOutlined, GlobalOutlined, FilterOutlined, PlusOutlined, FlagOutlined, DownloadOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { api, auth } from './api'

const { Title, Text } = Typography
const { TabPane } = Tabs

// ── Auth helpers ───────────────────────────────────────────────────────────────

function getStoredUser() {
  try { return JSON.parse(localStorage.getItem('crm_user') || 'null') }
  catch { return null }
}

// ── Login Page ─────────────────────────────────────────────────────────────────

function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await auth.login(email, password)
      localStorage.setItem('crm_token', res.access_token)
      localStorage.setItem('crm_user', JSON.stringify(res.user))
      message.success(`Welcome, ${res.user.full_name}`)
      onLogin(res.user)
    } catch (err) {
      console.error('Login error caught:', err, typeof err, err?.message, String(err))
      setError(String(err).substring(0, 200))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#001529',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Card style={{ width: 380, textAlign: 'center' }} styles={{ body: { padding: 32 } }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>📊</div>
          <Title level={4} style={{ margin: 0 }}>RankBuilder CRM</Title>
          <Text type="secondary">Sign in to your account</Text>
        </div>

        <form onSubmit={handleSubmit}>
          <Input
            size="large" type="email" placeholder="Email address"
            value={email} onChange={e => setEmail(e.target.value)}
            style={{ marginBottom: 12 }} required
          />
          <Input.Password
            size="large" placeholder="Password"
            value={password} onChange={e => setPassword(e.target.value)}
            style={{ marginBottom: 16 }} required
          />
          {error && <div style={{ color: '#ff4d4f', marginBottom: 12, fontSize: 13 }}>{error}</div>}
          <Button type="primary" htmlType="submit" loading={loading} block size="large">
            Sign In
          </Button>
        </form>

        <Divider style={{ margin: '20px 0 16px' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>DEMO ACCOUNTS</Text>
        </Divider>
        <div style={{ textAlign: 'left', fontSize: 12, color: '#888' }}>
          <div><Text code>craig@houseofsupreme.co.za</Text> — SYSTEM_ADMIN</div>
          <div><Text code>tiaan@houseofsupreme.co.za</Text> — CLIENT_ADMIN (HOS)</div>
        </div>
      </Card>
    </div>
  )
}

// ── Status / Type helpers ──────────────────────────────────────────────────────

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
  return <Tag color={cfg.color} icon={cfg.icon} style={{ borderRadius: 12 }}>{status}</Tag>
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
  const [days, setDays] = useState(30)

  const DATE_OPTIONS = [
    { label: '7 days',   value: 7   },
    { label: '30 days',  value: 30  },
    { label: '90 days',  value: 90  },
    { label: '6 months', value: 180 },
    { label: '1 year',   value: 365 },
  ]

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.dashboardSummary(clientId, days)
      setData(res)
    } catch (e) {
      message.error('Failed to load dashboard: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [clientId, days])

  if (loading) return <Spin style={{ display: 'block', margin: 60 }} />

  const { summary, source_breakdown } = data || {}

  // Response time badge colour: green < 2h, yellow < 8h, red >= 8h
  const rtColor = (h) => h == null ? '#999' : h < 2 ? '#52c41a' : h < 8 ? '#faad14' : '#ff4d4f'

  return (
    <div style={{ padding: '0 8px' }}>
      {/* ── KPI Row ───────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>Period:</Text>
        <Segmented
          options={DATE_OPTIONS}
          value={days}
          onChange={v => { setDays(v); setLoading(true) }}
          size="small"
        />
      </div>

      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        {[
          { label: 'Total Leads',    value: summary?.total_leads ?? 0,      color: '#1677ff' },
          { label: 'Qualified',      value: summary?.qualified_leads ?? 0,   suffix: `(${summary?.qualification_rate ?? 0}%)` },
          { label: 'Sent to Client', value: summary?.sent_to_client ?? 0,   color: '#1677ff' },
          { label: 'Converted',      value: summary?.converted ?? 0,        color: '#52c41a' },
          { label: 'Lost',           value: summary?.lost ?? 0,             color: '#ff4d4f' },
          { label: 'Conv. Rate',     value: `${summary?.conversion_rate ?? 0}%`, color: '#722ed1' },
        ].map((s, i) => (
          <Col xs={12} sm={8} md={4} key={i}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Statistic
                title={<Text type="secondary" style={{ fontSize: 11 }}>{s.label}</Text>}
                value={s.value}
                valueStyle={{ color: s.color || undefined, fontSize: 20 }}
                suffix={s.suffix && <Text type="secondary" style={{ fontSize: 11 }}>{s.suffix}</Text>}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Response Time ────────────────────────────────────────────── */}
      <Title level={5} style={{ margin: '16px 0 10px', color: '#555' }}>
        Response Time (NEW → Sent to Client)
      </Title>
      <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
        {[
          { label: 'Average',   value: summary?.avg_response_time_hours,  sub: 'mean' },
          { label: 'Median',    value: summary?.p50_response_time_hours,  sub: 'P50' },
          { label: '95th %ile', value: summary?.p95_response_time_hours,  sub: 'P95' },
        ].map((s, i) => {
          const colour = rtColor(s.value)
          return (
            <Col xs={12} sm={8} key={i}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: colour, lineHeight: 1 }}>
                  {s.value != null ? `${s.value}h` : '—'}
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>{s.label}</Text>
                {s.sub && <div><Text type="secondary" style={{ fontSize: 10 }}>{s.sub}</Text></div>}
              </Card>
            </Col>
          )
        })}
      </Row>

      {/* ── Leads Over Time Chart ─────────────────────────────────────── */}
      {data?.leads_over_time?.length > 0 && (
        <Card
          title="Lead Volume Over Time"
          size="small"
          style={{ marginBottom: 24 }}
          extra={<Text type="secondary" style={{ fontSize: 11 }}>Daily new leads</Text>}
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.leads_over_time} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d) => dayjs(d).format('MMM D')}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(v) => [`${v} lead${v === 1 ? '' : 's'}`, 'New']}
                labelFormatter={(d) => dayjs(d).format('DD MMM YYYY')}
              />
              <Bar dataKey="count" fill="#1677ff" radius={[3, 3, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* ── Source Performance Table ───────────────────────────────────── */}
      {source_breakdown?.length > 0 && (
        <Card
          title="Performance by Source"
          size="small"
          style={{ marginBottom: 24 }}
          bodyStyle={{ padding: '0 12px 12px' }}
        >
          <Table
            dataSource={source_breakdown.map(s => ({
              key: s.source,
              source: s.source?.replace('_', ' '),
              total: s.count,
              qualified: s.qualified_count,
              qualRate: s.count > 0 ? `${Math.round(s.qualified_count / s.count * 100)}%` : '—',
              avgRt: s.avg_response_time_hours != null ? `${s.avg_response_time_hours}h` : '—',
              sent: s.leads_sent,
              sourceKey: s.source,
            }))}
            columns={[
              { title: 'Source',     dataIndex: 'source',      width: 150 },
              { title: 'Leads',      dataIndex: 'total',       align: 'right' },
              { title: 'Qualified',  dataIndex: 'qualified',   align: 'right' },
              { title: 'Qual Rate',  dataIndex: 'qualRate',    align: 'center' },
              {
                title: 'Avg Response',
                dataIndex: 'avgRt',
                align: 'center',
                render: v => (
                  <Text style={{ color: rtColor(v?.replace('h','')), fontWeight: 600 }}>{v}</Text>
                ),
              },
              { title: 'Sent to Client', dataIndex: 'sent', align: 'right' },
            ]}
            pagination={false}
            size="small"
          />
        </Card>
      )}
    </div>
  )
}

// ── Leads ──────────────────────────────────────────────────────────────────────

const STATUS_OPTIONS = ['NEW','REVIEWED','QUALIFIED','SENT','CONTACTED','CONVERTED','LOST']
const SOURCE_OPTIONS  = ['HARO','CONNECTIVELY','GUEST_OUTREACH','WEBSITE','FACEBOOK','DIRECT_MAIL','CALL_IN','WEB_SEARCH','MANUAL']
const TYPE_OPTIONS    = ['VALID','INVALID','FOLLOW_UP']

export function LeadsTab({ clientId, refreshKey, campaignFilter, campaignName, onClearCampaign, canWrite = true }) {
  const [leads, setLeads] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({})
  const [search, setSearch] = useState('')
  const [selectedRow, setSelectedRow] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const loadLeads = async () => {
    setLoading(true)
    try {
      const params = { client_id: clientId, limit: pageSize, offset: (page - 1) * pageSize }
      if (campaignFilter) params.campaign_id = campaignFilter
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      if (filters.lead_type) params.lead_type = filters.lead_type
      if (search) params.search = search
      const res = await api.listLeads(params)
      setLeads(res.leads)
      setTotal(res.total)
    } catch (e) {
      message.error('Failed to load leads: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadLeads() }, [page, pageSize, filters, search, refreshKey, clientId, campaignFilter])

  const handleExport = async () => {
    try {
      const params = { client_id: clientId }
      if (campaignFilter) params.campaign_id = campaignFilter
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      if (filters.lead_type) params.lead_type = filters.lead_type
      if (search) params.search = search
      const csv = await api.exportLeads(params)
      // Trigger browser download
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `leads_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('Leads exported')
    } catch (e) {
      message.error('Export failed: ' + e.message)
    }
  }

  // Reset to page 1 when filters change (but not on page change itself)
  const prevFilters = useRef()
  useEffect(() => {
    const sig = JSON.stringify({ filters, search, campaignFilter, clientId })
    if (prevFilters.current && prevFilters.current !== sig && page !== 1) setPage(1)
    prevFilters.current = sig
  }, [filters, search, campaignFilter, clientId])

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
      title: 'Location',
      dataIndex: 'location',
      render: v => v ? <Text style={{ fontSize: 12 }}>{v}</Text> : '—',
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
      title: 'Resp. Time',
      width: 100,
      render: (_, r) => {
        if (!r.sent_to_client_at) return <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        const hours = Math.round((new Date(r.sent_to_client_at) - new Date(r.created_at)) / 3600000)
        const color = hours < 2 ? '#52c41a' : hours < 8 ? '#faad14' : '#ff4d4f'
        return <Text style={{ color, fontWeight: 600, fontSize: 12 }}>{hours}h</Text>
      },
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
      <Space wrap style={{ marginBottom: 12 }}>
        {campaignFilter && (
          <Tag closable color="geekblue" onClose={onClearCampaign}>
            <FlagOutlined /> {campaignName || 'Campaign'} filter
          </Tag>
        )}
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
        <Button onClick={handleExport} size="small" icon={<DownloadOutlined />}>
          Export
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>{total} leads</Text>
      </Space>

      <Table
        dataSource={leads}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page, pageSize, total,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          showSizeChanger: true,
          showTotal: t => `${t} leads`,
        }}
        size="small"
        scroll={{ x: 1200 }}
      />

      <LeadDrawer
        lead={selectedRow}
        open={drawerOpen}
        canWrite={canWrite}
        onClose={() => { setDrawerOpen(false); setSelectedRow(null) }}
        onUpdate={loadLeads}
      />
    </div>
  )
}

// ── Lead Drawer ────────────────────────────────────────────────────────────────

function LeadDrawer({ lead, open, onClose, onUpdate, canWrite = true }) {
  const [notes, setNotes] = useState('')
  const [clientResponse, setClientResponse] = useState('')
  const [status, setStatus] = useState(null)
  const [leadType, setLeadType] = useState(null)
  const [qualityScore, setQualityScore] = useState(null)
  const [location, setLocation] = useState('')
  const [saving, setSaving] = useState(false)
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [activeTab, setActiveTab] = useState('details')
  const [form] = Form.useForm()

  // Reset + fetch history when a lead is opened
  useEffect(() => {
    if (!lead || !open) return
    setNotes(lead.notes || '')
    setClientResponse(lead.client_response || '')
    setStatus(lead.status)
    setLeadType(lead.lead_type)
    setQualityScore(lead.quality_score)
    setLocation(lead.location || '')
    setActiveTab('details')
    setLoadingHistory(true)
    api.getLeadHistory(lead.id)
      .then(res => setHistory(res.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoadingHistory(false))
  }, [lead, open])

  const handleSave = async () => {
    if (!lead) return
    setSaving(true)
    try {
      await api.updateLead(lead.id, {
        notes,
        client_response: clientResponse,
        status,
        lead_type: leadType,
        quality_score: qualityScore,
        location,
        conversion_status:
          status === 'CONVERTED' ? 'CONVERTED' :
          status === 'LOST' ? 'LOST' : undefined,
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

  // ── History helpers ─────────────────────────────────────────────────────────

  const _fmt = (v) => v === 'None' || v === 'null' || !v ? '—' : v

  const _historyItems = history.map(h => {
    const field = h.field_changed
    const oldVal = _fmt(h.old_value)
    const newVal = _fmt(h.new_value)

    // Human-readable field labels
    const fieldLabel = {
      created: 'Lead Created',
      status: 'Status',
      lead_type: 'Lead Type',
      quality_score: 'Quality Score',
      notes: 'Notes',
      client_response: 'Client Response',
      pitch_sent: 'Pitch Sent',
      conversion_status: 'Conversion',
    }[field] || field

    // Coloured dot + description for the timeline
    const isCreate  = field === 'created'
    const isStatus  = field === 'status'
    const isType    = field === 'lead_type'
    const dotColor  = isCreate ? '#1677ff' : isStatus ? '#722ed1' : isType ? '#faad14' : '#52c41a'

    let desc = isCreate ? newVal
             : isStatus ? `${oldVal} → ${newVal}`
             : isType   ? `${oldVal} → ${newVal}`
             : `${field}: ${oldVal} → ${newVal}`

    return {
      key: h.id,
      color: dotColor,
      children: (
        <div>
          <Text strong style={{ fontSize: 13 }}>{fieldLabel}</Text>
          <br />
          <Text style={{ fontSize: 12, color: '#555' }}>{desc}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            {dayjs(h.changed_at).format('MMM D, YYYY HH:mm')}
            {h.changed_by !== 'system' && ` · ${h.changed_by}`}
          </Text>
        </div>
      ),
    }
  })

  // ── Computed fields ────────────────────────────────────────────────────────

  const responseTime = lead.sent_to_client_at
    ? `${Math.round((new Date(lead.sent_to_client_at) - new Date(lead.created_at)) / 3600000)}h`
    : null

  return (
    <Drawer
      title={
        <div>
          <Text strong style={{ fontSize: 15 }}>
            {lead.company_name || lead.contact_name || 'Lead Details'}
          </Text>
          <div style={{ marginTop: 4 }}>
            <StatusTag status={lead.status} />
            <Tag style={{ marginLeft: 6 }}>{lead.source?.replace('_', ' ')}</Tag>
            {lead.lead_type && <LeadTypeTag type={lead.lead_type} />}
          </div>
        </div>
      }
      placement="right" width={560}
      open={open} onClose={onClose}
      extra={
        canWrite ? (
          <Space>
            <Button onClick={onClose}>Cancel</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>Save Changes</Button>
          </Space>
        ) : (
          <Button onClick={onClose}>Close</Button>
        )
      }
    >
      {/* Tabs: Details | Activity */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ marginTop: -8 }}>
        <TabPane tab="Details" key="details">
          {/* Key metrics strip */}
          <Row gutter={12} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Card size="small" style={{ textAlign: 'center' }} bodyStyle={{ padding: '12px 8px' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#1677ff' }}>
                  {lead.quality_score ?? '—'}
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>Quality Score</Text>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ textAlign: 'center' }} bodyStyle={{ padding: '12px 8px' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: responseTime ? '#722ed1' : '#999' }}>
                  {responseTime ?? '—'}
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>Response Time</Text>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ textAlign: 'center' }} bodyStyle={{ padding: '12px 8px' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>
                  {lead.conversion_status || '—'}
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>Outcome</Text>
              </Card>
            </Col>
          </Row>

          {/* Contact info */}
          <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
            Contact Information
          </Title>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Company">{lead.company_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="Contact">{lead.contact_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="Email">
              {lead.contact_email
                ? <a href={`mailto:${lead.contact_email}`}>{lead.contact_email}</a>
                : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="Phone">{lead.contact_phone || '—'}</Descriptions.Item>
            <Descriptions.Item label="Website">
              {lead.company_website
                ? <a href={lead.company_website} target="_blank" rel="noreferrer">{lead.company_website}</a>
                : '—'}
            </Descriptions.Item>
            {lead.source_query && <Descriptions.Item label="Query/Article">{lead.source_query}</Descriptions.Item>}
            <Descriptions.Item label="Created">
              {dayjs(lead.created_at).format('YYYY-MM-DD HH:mm')}
            </Descriptions.Item>
            {lead.sent_to_client_at && (
              <Descriptions.Item label="Sent to Client">
                {dayjs(lead.sent_to_client_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
            )}
            {lead.converted_at && (
              <Descriptions.Item label="Converted At">
                {dayjs(lead.converted_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
            )}
          </Descriptions>

          {/* Attribution: Location + UTM */}
          {(lead.location || lead.utm_source || lead.utm_medium || lead.utm_campaign || lead.source_detail) && (
            <>
              <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
                Attribution
              </Title>
              <Descriptions column={1} bordered size="small">
                {lead.location && <Descriptions.Item label="Location">{lead.location}</Descriptions.Item>}
                {lead.source_detail && <Descriptions.Item label="Form\/Channel">{lead.source_detail}</Descriptions.Item>}
                {lead.utm_source && <Descriptions.Item label="UTM Source">{lead.utm_source}</Descriptions.Item>}
                {lead.utm_medium && <Descriptions.Item label="UTM Medium">{lead.utm_medium}</Descriptions.Item>}
                {lead.utm_campaign && <Descriptions.Item label="UTM Campaign">{lead.utm_campaign}</Descriptions.Item>}
              </Descriptions>
            </>
          )}

          {/* Message / Pitch */}
          {lead.message_excerpt && (
            <>
              <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
                Lead Message
              </Title>
              <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>
                {lead.message_excerpt}
              </div>
            </>
          )}

          {lead.pitch_sent && (
            <>
              <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
                Pitch Sent
              </Title>
              <div style={{ background: '#f0f7ff', padding: 12, borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>
                {lead.pitch_sent}
              </div>
            </>
          )}

          {/* Editable fields — admin only; VIEWER sees read-only summary */}
          <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
            Lead Status
          </Title>
          {canWrite ? (
            <Form layout="vertical" form={form}>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Status" style={{ marginBottom: 8 }}>
                    <Select value={status} onChange={setStatus} style={{ width: '100%' }}>
                      {STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Lead Type" style={{ marginBottom: 8 }}>
                    <Select value={leadType} onChange={setLeadType} allowClear placeholder="Select type" style={{ width: '100%' }}>
                      {TYPE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="Quality Score" style={{ marginBottom: 8 }}>
                <Rate value={qualityScore} onChange={setQualityScore} character={({ index = 0 }) => index + 1} style={{ fontSize: 18 }} />
                <Text type="secondary" style={{ marginLeft: 8 }}>{qualityScore ? `${qualityScore}/5` : ''}</Text>
              </Form.Item>
              <Form.Item label="Location" style={{ marginBottom: 8 }}>
                <Input
                  value={location}
                  onChange={e => setLocation(e.target.value)}
                  placeholder="e.g. Sandton, Johannesburg"
                />
              </Form.Item>
              <Form.Item label="Client Response" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  value={clientResponse}
                  onChange={e => setClientResponse(e.target.value)}
                  rows={2}
                  placeholder="What the client said / outcome..."
                />
              </Form.Item>
              <Form.Item label="Internal Notes" style={{ marginBottom: 0 }}>
                <Input.TextArea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={2}
                  placeholder="Private notes for the team..."
                />
              </Form.Item>
            </Form>
          ) : (
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Status"><StatusTag status={lead.status} /></Descriptions.Item>
              <Descriptions.Item label="Lead Type"><LeadTypeTag type={lead.lead_type} /></Descriptions.Item>
              <Descriptions.Item label="Quality Score">
                {lead.quality_score ? `${lead.quality_score}/5` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Location">{lead.location || '—'}</Descriptions.Item>
              {lead.client_response && <Descriptions.Item label="Client Response">{lead.client_response}</Descriptions.Item>}
              {lead.notes && <Descriptions.Item label="Notes">{lead.notes}</Descriptions.Item>}
            </Descriptions>
          )}
        </TabPane>

        <TabPane tab={
          <span>Activity <Badge count={history.length} size="small" style={{ marginLeft: 6 }} /></span>
        } key="history">
          {loadingHistory ? (
            <Spin style={{ display: 'block', marginTop: 40 }} />
          ) : _historyItems.length === 0 ? (
            <Empty description="No activity recorded yet" style={{ marginTop: 40 }} />
          ) : (
            <Timeline
              items={_historyItems}
              style={{ marginTop: 16 }}
            />
          )}
        </TabPane>
      </Tabs>
    </Drawer>
  )
}

// ── Campaigns Tab ───────────────────────────────────────────────────────────

const CAMPAIGN_STATUS_OPTIONS = ['ACTIVE','PAUSED','COMPLETED']

function CampaignStatusTag({ status }) {
  const map = { ACTIVE: 'success', PAUSED: 'warning', COMPLETED: 'default' }
  return <Tag color={map[status] || 'default'}>{status || '—'}</Tag>
}

function CampaignsTab({ clientId, refreshKey, onViewCampaignLeads, canWrite = true }) {
  const [campaigns, setCampaigns] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState(null)
  const [channelFilter, setChannelFilter] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)   // campaign being edited, or null for create
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const params = { client_id: clientId }
      if (statusFilter) params.status = statusFilter
      if (channelFilter) params.channel = channelFilter
      const res = await api.listCampaigns(params)
      setCampaigns(res.campaigns)
      setTotal(res.total)
    } catch (e) {
      message.error('Failed to load campaigns: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [clientId, statusFilter, channelFilter, refreshKey])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ status: 'ACTIVE' })
    setModalOpen(true)
  }

  const openEdit = (camp) => {
    setEditing(camp)
    form.setFieldsValue({
      name: camp.name,
      channel: camp.channel,
      status: camp.status,
    })
    setModalOpen(true)
  }

  const handleSave = async (values) => {
    setSaving(true)
    try {
      if (editing) {
        await api.updateCampaign(editing.id, values)
        message.success('Campaign updated')
      } else {
        await api.createCampaign({ ...values, client_id: clientId })
        message.success('Campaign created')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      message.error('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (camp) => {
    Modal.confirm({
      title: `Delete campaign "${camp.name}"?`,
      content: 'Leads already linked to this campaign will be kept (unlinked). This cannot be undone.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteCampaign(camp.id)
          message.success('Campaign deleted')
          load()
        } catch (e) {
          message.error('Delete failed: ' + e.message)
        }
      },
    })
  }

  const columns = [
    {
      title: 'Campaign',
      dataIndex: 'name',
      render: (v, r) => (
        <div>
          <Text strong>{v}</Text>
          <div style={{ fontSize: 11, color: '#888' }}>
            Created {dayjs(r.created_at).format('MMM D, YYYY')}
          </div>
        </div>
      ),
    },
    { title: 'Channel', dataIndex: 'channel', render: c => <Tag>{c?.replace('_', ' ')}</Tag>, width: 140 },
    { title: 'Status', dataIndex: 'status', render: s => <CampaignStatusTag status={s} />, width: 120 },
    { title: 'Leads', dataIndex: 'lead_count', align: 'right', width: 80 },
    { title: 'Qualified', dataIndex: 'qualified_count', align: 'right', width: 90 },
    { title: 'Converted', dataIndex: 'converted_count', align: 'right', width: 100 },
    {
      title: 'Qual Rate',
      width: 100,
      align: 'center',
      render: (_, r) => r.lead_count > 0
        ? <Text style={{ fontWeight: 600 }}>{Math.round(r.qualified_count / r.lead_count * 100)}%</Text>
        : <Text type="secondary">—</Text>,
    },
    {
      title: '',
      width: canWrite ? 180 : 100,
      render: (_, r) => (
        <Space size="small">
          <Button size="small" onClick={() => onViewCampaignLeads(r)}>View Leads</Button>
          {canWrite && <Button size="small" onClick={() => openEdit(r)}>Edit</Button>}
          {canWrite && (
            <Button size="small" danger onClick={() => handleDelete(r)}>
              <DeleteOutlined />
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <Space wrap>
          <Select allowClear placeholder="Status" style={{ width: 130 }} value={statusFilter}
            onChange={v => setStatusFilter(v)}>
            {CAMPAIGN_STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
          </Select>
          <Select allowClear placeholder="Channel" style={{ width: 160 }} value={channelFilter}
            onChange={v => setChannelFilter(v)}>
            {SOURCE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s.replace('_',' ')}</Select.Option>)}
          </Select>
          {(statusFilter || channelFilter) && (
            <Button size="small" onClick={() => { setStatusFilter(null); setChannelFilter(null) }}>
              <FilterOutlined /> Clear
            </Button>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>{total} campaign(s)</Text>
        </Space>
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            New Campaign
          </Button>
        )}
      </div>

      <Table
        dataSource={campaigns}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 10, showTotal: t => `${t} campaigns` }}
      />

      <Modal
        title={editing ? `Edit Campaign: ${editing.name}` : 'New Campaign'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        okText={editing ? 'Save Changes' : 'Create Campaign'}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
          <Form.Item name="name" label="Campaign Name" rules={[{ required: true, message: 'Name is required' }]}>
            <Input placeholder="e.g. HARO Q3 Security Push" />
          </Form.Item>
          <Form.Item name="channel" label="Channel" rules={[{ required: true, message: 'Channel is required' }]}>
            <Select placeholder="Select channel">
              {SOURCE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s.replace('_',' ')}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="status" label="Status">
            <Select>
              {CAMPAIGN_STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ── User Management Tab ───────────────────────────────────────────────────────

function UsersTab({ user: currentUser, clients }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [addForm] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.listUsers()
      setUsers(res)
    } catch (e) {
      message.error('Failed to load users: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAddUser = async (values) => {
    try {
      await api.createUser(values)
      message.success('User created')
      setModalOpen(false)
      addForm.resetFields()
      load()
    } catch (e) {
      message.error('Failed to create user: ' + e.message)
    }
  }

  const handleDelete = async (userId, userEmail) => {
    try {
      await api.deleteUser(userId)
      message.success(`User ${userEmail} disabled`)
      load()
    } catch (e) {
      message.error('Failed to delete user: ' + e.message)
    }
  }

  const columns = [
    { title: 'Name', dataIndex: 'full_name', render: v => <Text strong>{v}</Text> },
    { title: 'Email', dataIndex: 'email', render: v => <Text code style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: 'Role',
      dataIndex: 'role',
      render: r => <Tag color={r === 'SYSTEM_ADMIN' ? 'red' : r === 'CLIENT_ADMIN' ? 'blue' : 'default'}>{r}</Tag>,
    },
    {
      title: 'Client',
      dataIndex: 'client_id',
      render: (cid) => {
        if (!cid) return <Text type="secondary">—</Text>
        const c = clients.find(cl => cl.id === cid)
        return c ? c.company_name : cid
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      render: d => dayjs(d).format('MMM D, YYYY'),
    },
    {
      title: '',
      render: (_, r) => (
        r.id !== currentUser?.id && (
          <Button size="small" danger onClick={() => handleDelete(r.id, r.email)}>
            Disable
          </Button>
        )
      ),
      width: 80,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary">{users.length} user(s)</Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          Add User
        </Button>
      </div>

      <Table dataSource={users} columns={columns} rowKey="id" loading={loading} size="small" />

      <Modal
        title="Add User" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null}
        destroyOnClose
      >
        <Form form={addForm} layout="vertical" onFinish={handleAddUser} style={{ marginTop: 16 }}>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
            <Input placeholder="user@example.com" />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder="Min 8 characters" />
          </Form.Item>
          <Form.Item name="full_name" label="Full Name" rules={[{ required: true }]}>
            <Input placeholder="Jane Smith" />
          </Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true }]} initialValue="VIEWER">
            <Select>
              <Select.Option value="CLIENT_ADMIN">CLIENT_ADMIN — Full access to their client</Select.Option>
              <Select.Option value="VIEWER">VIEWER — Read-only access</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="client_id" label="Client" rules={[{ required: true }]}
            help="Leave as House of Supreme for HOS staff.">
            <Select placeholder="Select client" showSearch
              filterOption={(i, o) => o.props.children.toLowerCase().includes(i.toLowerCase())}>
              {clients.map(c => <Select.Option key={c.id} value={c.id}>{c.company_name}</Select.Option>)}
            </Select>
          </Form.Item>
          <Button type="primary" htmlType="submit" block>Create User</Button>
        </Form>
      </Modal>
    </div>
  )
}

// ── Main App ───────────────────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState(getStoredUser)
  const [clients, setClients] = useState([])
  const [selectedClientId, setSelectedClientId] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [refreshKey, setRefreshKey] = useState(0)
  const [campaignFilter, setCampaignFilter] = useState(null)
  const [campaignName, setCampaignName] = useState(null)

  // Listen for auth:logout events from api.js
  useEffect(() => {
    const handler = () => setUser(null)
    window.addEventListener('auth:logout', handler)
    return () => window.removeEventListener('auth:logout', handler)
  }, [])

  useEffect(() => {
    if (!user) return
    api.listClients().then(cs => {
      setClients(cs)
      if (cs.length > 0 && !selectedClientId) {
        const preferred = cs.find(c => c.id === user.client_id)
        setSelectedClientId(preferred ? preferred.id : cs[0].id)
      }
    }).catch(() => {
      message.error('Cannot connect to CRM backend. Is it running?')
    })
  }, [user])

  const handleLogin = (userData) => {
    setUser(userData)
    setTab('dashboard')
  }

  const handleLogout = () => {
    localStorage.removeItem('crm_token')
    localStorage.removeItem('crm_user')
    setUser(null)
    setClients([])
    setSelectedClientId(null)
  }

  // Not logged in → show login page
  if (!user) {
    return <LoginPage onLogin={handleLogin} />
  }

  const role = user.role
  const isAdmin = role === 'SYSTEM_ADMIN' || role === 'CLIENT_ADMIN'
  const isViewer = role === 'VIEWER'
  const canWrite = isAdmin  // VIEWER is read-only
  const isMultiClientAdmin = role === 'SYSTEM_ADMIN'

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      {/* Header */}
      <Layout.Header style={{ background: '#001529', display: 'flex', alignItems: 'center', gap: 16, padding: '0 24px' }}>
        <Title level={4} style={{ color: '#fff', margin: 0 }}>RankBuilder CRM</Title>

        {clients.length > 0 && isMultiClientAdmin && (
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

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: '#fff', fontSize: 13, lineHeight: 1.2 }}>{user.full_name}</div>
            <div style={{ color: '#fff5', fontSize: 11 }}>{user.role}</div>
          </div>
          <Button icon={<LogoutOutlined />} onClick={handleLogout}
            style={{ color: '#fff', borderColor: '#fff5' }} ghost size="small">
            Logout
          </Button>
        </div>
      </Layout.Header>

      {/* Content */}
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
                  campaignFilter={campaignFilter}
                  campaignName={campaignName}
                  canWrite={canWrite}
                  onClearCampaign={() => {
                    setCampaignFilter(null)
                    setCampaignName(null)
                  }}
                />
              </div>
            </TabPane>

            {isAdmin && (
              <TabPane tab={<span><FlagOutlined /> Campaigns</span>} key="campaigns">
                <div style={{ background: '#fff', borderRadius: 8, padding: 16 }}>
                  <CampaignsTab
                    clientId={selectedClientId}
                    refreshKey={refreshKey}
                    canWrite={canWrite}
                    onViewCampaignLeads={(camp) => {
                      setCampaignFilter(camp.id)
                      setCampaignName(camp.name)
                      setTab('leads')
                    }}
                  />
                </div>
              </TabPane>
            )}

            {isAdmin && (
              <TabPane tab={<span><UserOutlined /> Users</span>} key="users">
                <div style={{ background: '#fff', borderRadius: 8, padding: 16 }}>
                  <UsersTab user={user} clients={clients} />
                </div>
              </TabPane>
            )}
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

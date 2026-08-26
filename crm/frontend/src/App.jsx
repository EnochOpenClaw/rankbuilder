import { useState, useEffect, useRef } from 'react'
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd'
import {
  Layout, Typography, Card, Row, Col, Statistic, Table, Tag, Button,
  Drawer, Descriptions, Timeline, Select, Input, Space, message, Tabs,
  Progress, Empty, Spin, Badge, Modal, Form, Divider, Segmented, Rate, InputNumber, Checkbox, DatePicker, TimePicker, Alert, Grid, Menu, Dropdown
} from 'antd'
import {
  DashboardOutlined, DatabaseOutlined, UserOutlined, LogoutOutlined,
  CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined,
  SendOutlined, GlobalOutlined, FilterOutlined, PlusOutlined, FlagOutlined, DownloadOutlined,
  PaperClipOutlined, UploadOutlined, TagsOutlined, ThunderboltOutlined, AppstoreOutlined, BarChartOutlined, RobotOutlined, CopyOutlined, QuestionCircleOutlined, FolderOpenOutlined, RollbackOutlined, FieldTimeOutlined, MenuOutlined, KeyOutlined, MailOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { api, auth } from './api'

const { Title, Text } = Typography
const { TabPane } = Tabs

// Only these users may PERMANENTLY delete leads. Everyone else can Archive/Restore.
const DELETE_ALLOWED_EMAILS = ['craig@houseofsupreme.co.za']


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
  const [mustChange, setMustChange] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await auth.login(email, password)
      localStorage.setItem('crm_token', res.access_token)
      localStorage.setItem('crm_user', JSON.stringify(res.user))
      message.success(`Welcome, ${res.user.full_name}`)
      if (res.user.must_change_password) {
        // Force the user to set a new password before entering the app
        setMustChange(true)
      } else {
        onLogin(res.user)
      }
    } catch (err) {
      console.error('Login error caught:', err, typeof err, err?.message, String(err))
      setError(String(err).substring(0, 200))
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordChanged = async (newPassword) => {
    try {
      await api.changePassword(password, newPassword)
      // Update the stored user (must_change_password now false)
      const stored = JSON.parse(localStorage.getItem('crm_user') || 'null')
      if (stored) {
        stored.must_change_password = 0
        localStorage.setItem('crm_user', JSON.stringify(stored))
        onLogin(stored)
      } else {
        onLogin(JSON.parse(localStorage.getItem('crm_user') || '{}'))
      }
    } catch (err) {
      throw err
    }
  }

  if (mustChange) {
    return <ChangePasswordScreen
      email={email}
      onDone={handlePasswordChanged}
      onCancel={() => { setMustChange(false); onLogin(JSON.parse(localStorage.getItem('crm_user') || 'null')) }}
    />
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#001529',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '24px 16px',
    }}>
      <Card style={{ width: '100%', maxWidth: 380, textAlign: 'center' }} styles={{ body: { padding: 32 } }}>
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
          <Text type="secondary" style={{ fontSize: 12 }}>Login</Text>
        </Divider>
      </Card>
    </div>
  )
}

// ── Force password change on first login ─────────────────────────────────────

function ChangePasswordScreen({ email, onDone, onCancel }) {
  const [newPass, setNewPass] = useState('')
  const [confirmPass, setConfirmPass] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (newPass.length < 8) { setError('Password must be at least 8 characters'); return }
    if (newPass !== confirmPass) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      await onDone(newPass)
    } catch (err) {
      setError(String(err.message || err).substring(0, 200))
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#001529', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Card style={{ width: 380, textAlign: 'center' }} styles={{ body: { padding: 32 } }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 44, marginBottom: 8 }}>🔒</div>
          <Title level={4} style={{ margin: 0 }}>Change Your Password</Title>
          <Text type="secondary">First-time login — please set a new password</Text>
        </div>
        <div style={{ marginBottom: 16, fontSize: 12, color: '#888' }}>Account: {email}</div>
        <form onSubmit={handleSubmit}>
          <Input.Password size="large" placeholder="New password (min 8 characters)"
            value={newPass} onChange={e => setNewPass(e.target.value)}
            style={{ marginBottom: 12 }} required />
          <Input.Password size="large" placeholder="Confirm new password"
            value={confirmPass} onChange={e => setConfirmPass(e.target.value)}
            style={{ marginBottom: 12 }} required />
          {error && <div style={{ color: '#ff4d4f', marginBottom: 12, fontSize: 13 }}>{error}</div>}
          <Button type="primary" htmlType="submit" loading={loading} block size="large">
            Update Password
          </Button>
        </form>
        <div style={{ marginTop: 12 }}>
          <Button type="link" size="small" onClick={onCancel}>Skip for now</Button>
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
  if (!score && score !== 0) return <Text type="secondary">—</Text>
  // Auto-scored leads use 0-100 scale; legacy manual scores use 1-5
  if (score > 5) {
    const color = score >= 70 ? '#f5222d' : score >= 40 ? '#fa8c16' : '#8c8c8c'
    const label = score >= 70 ? 'HOT' : score >= 40 ? 'WARM' : 'COLD'
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Progress percent={score} size="small" strokeColor={color} style={{ width: 50 }} />
        <Tag color={color} style={{ fontSize: 10, margin: 0 }}>{label}</Tag>
      </div>
    )
  }
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

  const { summary, source_breakdown, rep_breakdown } = data || {}

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

      {/* ── Lead Pipeline Funnel ───────────────────────────────────────── */}
      {data?.funnel?.length > 0 && (
        <Card
          title="Lead Pipeline Funnel"
          size="small"
          style={{ marginBottom: 24 }}
          extra={<Text type="secondary" style={{ fontSize: 11 }}>Leads at each stage</Text>}
        >
          {data.funnel.map((stage, i) => {
            const maxCount = Math.max(...data.funnel.map(s => s.count), 1)
            const isConverted = stage.stage === 'Converted'
            const isLost = stage.stage === 'Lost'
            const color = isConverted ? '#52c41a' : isLost ? '#ff4d4f' : '#1677ff'
            const widthPct = maxCount > 0 ? Math.round((stage.count / maxCount) * 100) : 0
            return (
              <div key={stage.stage} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                  <Text style={{ color: '#555' }}>{stage.stage}</Text>
                  <Text strong style={{ color }}>{stage.count}</Text>
                </div>
                <div style={{ background: '#f0f0f0', borderRadius: 4, height: 20, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.max(widthPct, stage.count > 0 ? 4 : 0)}%`,
                      height: '100%',
                      background: color,
                      borderRadius: 4,
                      transition: 'width 0.5s ease',
                      opacity: isLost ? 0.5 : 0.85,
                    }}
                  />
                </div>
              </div>
            )
          })}
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

      {/* ── Rep Productivity ───────────────────────────────────────────── */}
      {rep_breakdown?.length > 0 && (
        <Card
          title="Sales Rep Productivity"
          size="small"
          style={{ marginBottom: 24 }}
          bodyStyle={{ padding: '0 12px 12px' }}
          extra={
            <Text type="secondary" style={{ fontSize: 11 }}>
              Assigned leads & follow-up activity
            </Text>
          }
        >
          <Table
            dataSource={rep_breakdown.map(r => ({
              key: r.rep_email,
              rep: r.rep_name || r.rep_email,
              assigned: r.assigned_leads,
              followUps: r.follow_ups,
              contacted: r.contacted,
              converted: r.converted,
              lost: r.lost,
              lastFu: r.last_follow_up_at ? dayjs(r.last_follow_up_at).format('MMM D, HH:mm') : '—',
            }))}
            columns={[
              { title: 'Sales Rep', dataIndex: 'rep', width: 160 },
              { title: 'Assigned Leads', dataIndex: 'assigned', align: 'right' },
              { title: 'Follow-ups', dataIndex: 'followUps', align: 'right' },
              { title: 'Contacted', dataIndex: 'contacted', align: 'right' },
              {
                title: 'Converted',
                dataIndex: 'converted',
                align: 'right',
                render: v => <Text style={{ color: '#52c41a', fontWeight: 600 }}>{v}</Text>,
              },
              {
                title: 'Lost',
                dataIndex: 'lost',
                align: 'right',
                render: v => <Text style={{ color: '#ff4d4f' }}>{v}</Text>,
              },
              { title: 'Last Follow-up', dataIndex: 'lastFu', align: 'center' },
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
const SOURCE_OPTIONS  = ['HARO','CONNECTIVELY','GUEST_OUTREACH','WEBSITE','FACEBOOK','DIRECT_MAIL','CALL_IN','WEB_SEARCH','MANUAL','ROADSIDE','PPC','WORD_OF_MOUTH']
const TYPE_OPTIONS    = ['VALID','INVALID','FOLLOW_UP']

// Format a phone number as ### ### #### (digits only, max 10)
function formatPhone(v) {
  const digits = (v || '').replace(/[^0-9]/g, '').slice(0, 10)
  if (digits.length <= 3) return digits
  if (digits.length <= 6) return `${digits.slice(0,3)} ${digits.slice(3)}`
  return `${digits.slice(0,3)} ${digits.slice(3,6)} ${digits.slice(6)}`
}

export function LeadsTab({ clientId, refreshKey, campaignFilter, campaignName, onClearCampaign, canWrite = true, sources = [], onSourcesChange, currentUserEmail = '' }) {
  const [leads, setLeads] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({})
  const [search, setSearch] = useState('')
  const [selectedRow, setSelectedRow] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [createMode, setCreateMode] = useState(false)
  const [repOptions, setRepOptions] = useState([])
  const [viewMode, setViewMode] = useState('table')

  // Partner hand-off (e.g. send a lead to Southern Shutters / Sian)
  const [handoffLead, setHandoffLead] = useState(null)
  const [handoffClients, setHandoffClients] = useState([])
  const [handoffTargets, setHandoffTargets] = useState([])
  const [handoffClientId, setHandoffClientId] = useState(null)
  const [handoffTargetEmail, setHandoffTargetEmail] = useState(null)
  const [handoffSaving, setHandoffSaving] = useState(false)

  const openHandoff = (r) => {
    setHandoffLead(r)
    setHandoffClientId(null)
    setHandoffTargetEmail(null)
    setHandoffTargets([])
    // Load partner clients (all clients except the current one)
    api.listClients().then(cs => {
      const others = (cs || []).filter(c => c.id !== clientId)
      setHandoffClients(others)
    }).catch(() => setHandoffClients([]))
  }

  const onHandoffClientChange = (cid) => {
    setHandoffClientId(cid)
    setHandoffTargetEmail(null)
    // Load that client's active users
    api.listUsers().then(us => {
      const targets = (us || []).filter(u => u.client_id === cid && u.is_active && u.role !== 'SYSTEM_ADMIN')
      setHandoffTargets(targets)
    }).catch(() => setHandoffTargets([]))
  }

  const doHandoff = async () => {
    if (!handoffLead || !handoffClientId || !handoffTargetEmail) {
      message.warning('Select a partner client and target user')
      return
    }
    setHandoffSaving(true)
    try {
      const res = await api.handoffLead(handoffLead.id, { partner_client_id: handoffClientId, target_user_email: handoffTargetEmail })
      message.success('Lead handed to partner')
      setHandoffLead(null)
      loadLeads()
    } catch (e) {
      message.error('Handoff failed: ' + e.message)
    } finally {
      setHandoffSaving(false)
    }
  }

  // Load assignable sales reps (AGENT + CLIENT_ADMIN) for this client — drives the
  // assignment dropdown dynamically instead of a hardcoded list (2026-08-19).
  useEffect(() => {
    let alive = true
    api.listUsers()
      .then(users => {
        if (!alive) return
        const assignable = (users || []).filter(u =>
          (u.role === 'AGENT' || u.role === 'CLIENT_ADMIN') &&
          (!clientId || u.client_id === clientId)
        ).map(u => ({ email: u.email, name: u.full_name || u.email }))
        setRepOptions(assignable)
      })
      .catch(() => { /* non-fatal: fall back to empty list */ })
    return () => { alive = false }
  }, [clientId])

  const loadLeads = async () => {
    setLoading(true)
    try {
      const params = { client_id: clientId, limit: pageSize, offset: (page - 1) * pageSize }
      if (campaignFilter) params.campaign_id = campaignFilter
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      if (filters.lead_type) params.lead_type = filters.lead_type
      if (filters.assigned_to) params.assigned_to = filters.assigned_to
      if (filters.archived) params.include_archived = true
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

  const handleArchive = async (r) => {
    try {
      await api.archiveLead(r.id)
      message.success("Lead archived")
      loadLeads()
    } catch (e) {
      message.error("Archive failed: " + e.message)
    }
  }

  const handleRestore = async (r) => {
    try {
      await api.restoreLead(r.id)
      message.success("Lead restored")
      loadLeads()
    } catch (e) {
      message.error("Restore failed: " + e.message)
    }
  }

  const handleDelete = async (r) => {
    Modal.confirm({
      title: 'Permanently delete lead "' + (r.company_name || r.contact_email || r.id) + '"?',
      content: "This permanently removes the lead and all its history/activity. This cannot be undone.",
      okText: "Delete forever",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteLead(r.id)
          message.success("Lead deleted")
          loadLeads()
        } catch (e) {
          message.error("Delete failed: " + e.message)
        }
      },
    })
  }

  const handleExport = async () => {
    try {
      const params = { client_id: clientId }
      if (campaignFilter) params.campaign_id = campaignFilter
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      if (filters.lead_type) params.lead_type = filters.lead_type
      if (filters.assigned_to) params.assigned_to = filters.assigned_to
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
      title: 'Assigned',
      dataIndex: 'assigned_to_name',
      render: (v, r) => v ? (
        <Tag color={r.assigned_to === 'richard@houseofsupreme.co.za' ? 'geekblue' : r.assigned_to === 'tiaan@houseofsupreme.co.za' ? 'purple' : 'green'} style={{ fontSize: 11 }}>
          {v}
        </Tag>
      ) : '—',
      width: 110,
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
      title: 'Payment',
      dataIndex: 'payment_status',
      render: p => p === 'RECEIVED' ? <Tag color="green">Paid ✓</Tag> : p === 'PENDING' ? <Tag color="orange">Pending</Tag> : '—',
      width: 90,
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
        <Space size={4}>
          <Button size="small" onClick={() => { setSelectedRow(r); setDrawerOpen(true) }}>
            View
          </Button>
          {r.archived ? (
            <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRestore(r)}>
              Restore
            </Button>
          ) : (
            <Button size="small" icon={<FolderOpenOutlined />} onClick={() => handleArchive(r)}>
              Archive
            </Button>
          )}
          {!r.archived && DELETE_ALLOWED_EMAILS.includes(currentUserEmail) && (
            <Button size="small" icon={<SendOutlined />} onClick={() => openHandoff(r)}>
              Hand to Partner
            </Button>
          )}
          {canWrite && DELETE_ALLOWED_EMAILS.includes(currentUserEmail) && (
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)} />
          )}
        </Space>
      ),
      width: 210,
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
          {(sources.length ? sources : SOURCE_OPTIONS.map(c => ({ code: c, name: c }))).map(s => <Select.Option key={s.code} value={s.code}>{s.name}</Select.Option>)}
        </Select>
        <Select allowClear placeholder="Assigned to" style={{ width: 160 }}
          value={filters.assigned_to}
          onChange={v => { setFilters(f => ({ ...f, assigned_to: v })); setPage(1) }}>
          {repOptions.map(r => <Select.Option key={r.email} value={r.email}>{r.name}</Select.Option>)}
        </Select>
        <Select allowClear placeholder="Type" style={{ width: 120 }}
          onChange={v => { setFilters(f => ({ ...f, lead_type: v })); setPage(1) }}>
          {TYPE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
        </Select>
        <Select allowClear placeholder="Score" style={{ width: 100 }}
          onChange={v => { setFilters(f => ({ ...f, quality_score: v })); setPage(1) }}>
          {[0,10,20,30,40,50,60,70,80,90,100].map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
        </Select>
        <Button
          size="small"
          type={filters.archived ? 'primary' : 'default'}
          icon={<FolderOpenOutlined />}
          onClick={() => { setFilters(f => ({ ...f, archived: f.archived ? undefined : true })); setPage(1) }}
        >
          {filters.archived ? 'Show Active' : 'Show Archived'}
        </Button>
        <Button onClick={() => setFilters({})} size="small">
          <FilterOutlined /> Clear
        </Button>
        <Button onClick={handleExport} size="small" icon={<DownloadOutlined />}>
          Export
        </Button>
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />}
            onClick={() => { setCreateMode(true); setDrawerOpen(true) }}>
            Add Lead
          </Button>
        )}
        <Text type="secondary" style={{ fontSize: 12 }}>{total} leads</Text>
      </Space>

      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end' }}>
        <Segmented
          value={viewMode}
          onChange={setViewMode}
          options={[
            { label: 'Table', value: 'table', icon: <DatabaseOutlined /> },
            { label: 'Board', value: 'board', icon: <AppstoreOutlined /> },
          ]}
          size="small"
        />
      </div>

      {viewMode === 'board' ? (
        <KanbanBoard
          clientId={clientId}
          canWrite={canWrite}
          onUpdate={loadLeads}
          onOpenLead={(lead) => { setSelectedRow(lead); setDrawerOpen(true) }}
        />
      ) : (
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
      )}

      <LeadDrawer
        lead={selectedRow}
        open={drawerOpen}
        canWrite={canWrite}
        clientId={clientId}
        createMode={createMode}
        repOptions={repOptions}
        sources={sources}
        onClose={() => { setDrawerOpen(false); setSelectedRow(null); setCreateMode(false) }}
        onUpdate={loadLeads}
      />
    </div>
  )
}

// ── Kanban Pipeline Board ──────────────────────────────────────────────────────

const KANBAN_COLUMNS = ['NEW', 'REVIEWED', 'QUALIFIED', 'SENT', 'CONTACTED', 'CONVERTED', 'LOST']

function KanbanBoard({ clientId, canWrite = true, onUpdate, onOpenLead }) {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.listLeads({ client_id: clientId, limit: 200 })
      setLeads(res.leads || [])
    } catch (e) {
      message.error('Failed to load board: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [clientId])

  const moveLead = async (leadId, newStatus) => {
    // Optimistic update
    setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status: newStatus } : l))
    try {
      await api.updateLead(leadId, { status: newStatus })
      onUpdate && onUpdate()
    } catch (e) {
      message.error('Move failed: ' + e.message)
      load() // revert
    }
  }

  const onDragEnd = (result) => {
    if (!result.destination) return
    const { draggableId, destination } = result
    const newStatus = destination.droppableId
    if (result.source.droppableId === newStatus) return
    moveLead(draggableId, newStatus)
  }

  const daysInStage = (lead) => {
    const base = lead.updated_at || lead.created_at
    if (!base) return 0
    return Math.max(0, Math.round((Date.now() - new Date(base).getTime()) / 86400000))
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 12 }}>
        {KANBAN_COLUMNS.map(status => {
          const colLeads = leads.filter(l => l.status === status)
          return (
            <Droppable key={status} droppableId={status}>
              {(provided, snapshot) => (
                <div
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                  style={{
                    background: snapshot.isDraggingOver ? '#f0f5ff' : '#fafafa',
                    borderRadius: 8, padding: 8, width: 220, minHeight: 200, flexShrink: 0,
                    border: '1px solid #f0f0f0',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <Tag color={status === 'CONVERTED' ? 'green' : status === 'LOST' ? 'red' : status === 'NEW' ? 'blue' : 'default'}>{status}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>{colLeads.length}</Text>
                  </div>
                  {colLeads.map((lead, idx) => (
                    <Draggable key={lead.id} draggableId={lead.id} index={idx} isDragDisabled={!canWrite}>
                      {(p2) => (
                        <div
                          ref={p2.innerRef}
                          {...p2.draggableProps}
                          {...p2.dragHandleProps}
                          onClick={() => onOpenLead && onOpenLead(lead)}
                          style={{
                            ...p2.draggableProps.style,
                            background: '#fff', borderRadius: 6, padding: 8, marginBottom: 8,
                            border: '1px solid #e8e8e8', boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                            cursor: canWrite ? 'grab' : 'default',
                          }}
                        >
                          <div style={{ fontWeight: 600, fontSize: 13 }}>{lead.company_name || lead.contact_name || 'Lead'}</div>
                          {lead.contact_name && lead.company_name && (
                            <div style={{ color: '#888', fontSize: 12 }}>{lead.contact_name}</div>
                          )}
                          <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                            <Tag style={{ fontSize: 10, margin: 0 }}>{lead.source?.replace('_', ' ')}</Tag>
                            {lead.quality_score ? (
                              <Tag color={lead.quality_score >= 70 ? 'red' : lead.quality_score >= 40 ? 'orange' : 'default'} style={{ fontSize: 10, margin: 0 }}>
                                {lead.quality_score}
                              </Tag>
                            ) : null}
                          </div>
                          <div style={{ marginTop: 6, fontSize: 11, color: '#aaa' }}>{daysInStage(lead)}d</div>
                        </div>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          )
        })}
      </div>
    </DragDropContext>
  )
}

// ── Lead Drawer ────────────────────────────────────────────────────────────────

function LeadDrawer({ lead, open, onClose, onUpdate, canWrite = true, repOptions = [], clientId = null, createMode = false, sources = [] }) {
  const [notes, setNotes] = useState('')
  const [clientResponse, setClientResponse] = useState('')
  const [status, setStatus] = useState(null)
  const [leadType, setLeadType] = useState(null)
  const [qualityScore, setQualityScore] = useState(null)
  const [quoteAmount, setQuoteAmount] = useState(null)
  const [paymentStatus, setPaymentStatus] = useState(null)
  const [location, setLocation] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [companyWebsite, setCompanyWebsite] = useState('')
  const [address, setAddress] = useState('')
  // Create-mode fields (new lead form)
  const [createSource, setCreateSource] = useState('MANUAL')
  const [createSourceDetail, setCreateSourceDetail] = useState('')
  const [createMessage, setCreateMessage] = useState('')
  const [countryCode, setCountryCode] = useState('+27')
  const [saving, setSaving] = useState(false)
  const [draftLoading, setDraftLoading] = useState(false)
  const [draft, setDraft] = useState(null)
  const [draftError, setDraftError] = useState(null)
  const [draftModalOpen, setDraftModalOpen] = useState(false)
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [activeTab, setActiveTab] = useState('details')
  const [followUpNote, setFollowUpNote] = useState('')
  const [followUpType, setFollowUpType] = useState('CALL')
  const [followUpOutcome, setFollowUpOutcome] = useState(null)
  const [assignEmail, setAssignEmail] = useState('')
  const [assignName, setAssignName] = useState('')
  const [savingFollowUp, setSavingFollowUp] = useState(false)
  const [savingAssign, setSavingAssign] = useState(false)
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [docCategory, setDocCategory] = useState('OTHER')
  const [reminders, setReminders] = useState([])
  const [loadingReminders, setLoadingReminders] = useState(false)
  const [remindDate, setRemindDate] = useState(null)
  const [remindTime, setRemindTime] = useState(null)
  const [remindNote, setRemindNote] = useState('')
  const [savingReminder, setSavingReminder] = useState(false)
  const [emails, setEmails] = useState([])
  const [loadingEmails, setLoadingEmails] = useState(false)
  const [activities, setActivities] = useState([])
  const [loadingActivities, setLoadingActivities] = useState(false)
  const [form] = Form.useForm()

  // Reset + fetch history when a lead is opened
  useEffect(() => {
    if (!lead || !open) return
    setNotes(lead.notes || '')
    setClientResponse(lead.client_response || '')
    setStatus(lead.status)
    setLeadType(lead.lead_type)
    setQualityScore(lead.quality_score)
    setQuoteAmount(lead.quote_amount || null)
    setPaymentStatus(lead.payment_status || null)
    setLocation(lead.location || '')
    setContactName(lead.contact_name || '')
    setContactEmail(lead.contact_email || '')
    setContactPhone(lead.contact_phone || '')
    setCompanyName(lead.company_name || '')
    setCompanyWebsite(lead.company_website || '')
    setAddress(lead.address || '')
    setFollowUpNote('')
    setAssignEmail(lead.assigned_to || '')
    setAssignName(lead.assigned_to_name || '')
    setActiveTab('details')
    setLoadingHistory(true)
    api.getLeadHistory(lead.id)
      .then(res => setHistory(res.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoadingHistory(false))
    setLoadingDocs(true)
    api.listDocuments(lead.id)
      .then(res => setDocuments(res.documents || []))
      .catch(() => setDocuments([]))
      .finally(() => setLoadingDocs(false))
    setLoadingReminders(true)
    api.listReminders(lead.id)
      .then(res => setReminders(res.reminders || []))
      .catch(() => setReminders([]))
      .finally(() => setLoadingReminders(false))
    setLoadingEmails(true)
    api.listEmails(lead.id)
      .then(res => setEmails(res.emails || []))
      .catch(() => setEmails([]))
      .finally(() => setLoadingEmails(false))
    setLoadingActivities(true)
    api.listActivities(lead.id)
      .then(res => setActivities(res.activities || []))
      .catch(() => setActivities([]))
      .finally(() => setLoadingActivities(false))
    setRemindDate(null)
    setRemindTime(null)
    setRemindNote('')
  }, [lead, open])

  const handleCreate = async () => {
    if (!contactName && !companyName && !contactEmail && !contactPhone) {
      message.warning('Please enter at least a name, company or contact detail')
      return
    }
    // Validate email format if provided: name@company.tld
    if (contactEmail) {
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(contactEmail.trim())
      if (!emailOk) {
        message.error('Please enter a valid email address (e.g. name@company.co.za)')
        return
      }
    }
    // Validate phone if provided: digits only (country code handled separately)
    if (contactPhone) {
      const digits = contactPhone.replace(/[^0-9]/g, '')
      if (digits.length < 9 || digits.length > 10) {
        message.error('Please enter a valid phone number (e.g. 082 555 1234)')
        return
      }
    }
    setSaving(true)
    try {
      await api.createLead({
        client_id: clientId,
        source: createSource,
        source_detail: createSourceDetail || undefined,
        contact_name: contactName || undefined,
        contact_email: contactEmail ? contactEmail.trim() : undefined,
        contact_phone: contactPhone ? `${countryCode} ${contactPhone.trim()}` : undefined,
        company_name: companyName || undefined,
        company_website: companyWebsite || undefined,
        location: location || undefined,
        lead_type: leadType || undefined,
        quality_score: qualityScore || undefined,
        quote_amount: quoteAmount || undefined,
        message_excerpt: createMessage || undefined,
        notes: notes || undefined,
      })
      message.success('Lead created')
      onUpdate()
      onClose()
    } catch (e) {
      message.error('Create failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleScheduleReminder = async () => {
    if (!lead) return
    if (!remindDate || !remindTime) {
      message.warning('Please pick a date and time for the reminder')
      return
    }
    const dt = dayjs(remindDate)
      .hour(dayjs(remindTime).hour())
      .minute(dayjs(remindTime).minute())
      .second(0)
    if (dt.isBefore(dayjs())) {
      message.warning('Reminder time must be in the future')
      return
    }
    setSavingReminder(true)
    try {
      await api.createReminder(lead.id, {
        remind_at: dt.toISOString(),
        note: remindNote || undefined,
      })
      message.success('Reminder scheduled')
      setRemindDate(null)
      setRemindTime(null)
      setRemindNote('')
      const res = await api.listReminders(lead.id)
      setReminders(res.reminders || [])
    } catch (e) {
      message.error('Failed to schedule reminder: ' + e.message)
    } finally {
      setSavingReminder(false)
    }
  }

  const handleDownloadDoc = async (doc) => {
    try {
      const blob = await api.downloadDocument(lead.id, doc.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = doc.filename || 'document'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(e.message || 'Download failed')
    }
  }

  const handleDismissReminder = async (rid) => {
    try {
      await api.dismissReminder(lead.id, rid)
      message.success('Reminder dismissed')
      const res = await api.listReminders(lead.id)
      setReminders(res.reminders || [])
    } catch (e) {
      message.error('Failed to dismiss reminder: ' + e.message)
    }
  }

  const handleSave = async () => {
    if (!lead) return
    // Validate email format if provided
    if (contactEmail) {
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(contactEmail.trim())
      if (!emailOk) {
        message.error('Please enter a valid email address (e.g. name@company.co.za)')
        return
      }
    }
    // Quality score required when qualifying or converting (0-100 scale; 0 is valid)
    if ((status === 'QUALIFIED' || status === 'CONVERTED') && (qualityScore === null || qualityScore === undefined || qualityScore === '')) {
      message.warning('Please set a Quality Score (0-100) before marking this lead as ' + status)
      setActiveTab('details')
      return
    }
    setSaving(true)
    try {
      await api.updateLead(lead.id, {
        notes,
        client_response: clientResponse,
        status,
        lead_type: leadType,
        quality_score: qualityScore,
        quote_amount: quoteAmount,
        payment_status: paymentStatus,
        location,
        contact_name: contactName,
        contact_email: contactEmail ? contactEmail.trim() : undefined,
        contact_phone: contactPhone,
        company_name: companyName,
        company_website: companyWebsite,
        address,
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

  const handleDraftReply = async () => {
    if (!lead) return
    setDraftLoading(true)
    setDraftError(null)
    setDraft(null)
    try {
      const res = await api.draftReply(lead.id)
      if (res.draft) {
        setDraft(res.draft)
        setDraftModalOpen(true)
      } else {
        setDraftError(res.error || 'Failed to generate draft')
        message.error(res.error || 'Failed to generate draft')
      }
    } catch (e) {
      setDraftError(e.message)
      message.error('AI draft failed: ' + e.message)
    } finally {
      setDraftLoading(false)
    }
  }

  if (!lead && !createMode) return null

  // ── Follow-up & assignment handlers ───────────────────────────────────────

  const handleLogFollowUp = async () => {
    if (!followUpNote.trim()) {
      message.warning('Please describe the follow-up action')
      return
    }
    setSavingFollowUp(true)
    try {
      await api.logFollowUp(lead.id, {
        note: followUpNote,
        activity_type: followUpType || 'CALL',
        outcome: followUpOutcome || undefined,
      })
      message.success('Follow-up logged')
      setFollowUpNote('')
      setFollowUpOutcome(null)
      // Refresh history + lead
      const h = await api.getLeadHistory(lead.id)
      setHistory(h.history || [])
      api.listActivities(lead.id).then(res => setActivities(res.activities || [])).catch(() => {})
      onUpdate()
    } catch (e) {
      message.error('Failed to log follow-up: ' + e.message)
    } finally {
      setSavingFollowUp(false)
    }
  }

  const handleAssign = async () => {
    if (!assignEmail) {
      message.warning('Select a sales rep')
      return
    }
    setSavingAssign(true)
    try {
      await api.assignLead(lead.id, { assigned_to: assignEmail, assigned_to_name: assignName })
      message.success('Lead assigned')
      onUpdate()
    } catch (e) {
      message.error('Assign failed: ' + e.message)
    } finally {
      setSavingAssign(false)
    }
  }

  const REP_OPTIONS = repOptions

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

  const _notificationTypeLabel = (t) => ({
    new_lead: 'New Lead',
    lead_allocated: 'Lead Allocated',
    lead_sent: 'Pitch Sent',
    hot_lead: 'Hot Lead',
    sla_breach: 'SLA Breach',
    follow_up: 'Follow-up Due',
    reminder: 'Reminder',
    manual: 'Manual Email',
  }[t] || t || 'Notification')

  const _activityTypeLabel = (t) => ({
    CALL: '📞 Call',
    EMAIL: '✉️ Email',
    WHATSAPP: '💬 WhatsApp',
    SMS: '📱 SMS',
    NOTE: '📝 Note',
    OTHER: 'Other',
  }[t] || t || 'Activity')

  const _outcomeLabel = (o) => ({
    NO_ANSWER: 'No answer',
    LEFT_VOICEMAIL: 'Left voicemail',
    SPOKE: 'Spoke to client',
    SENT: 'Sent (quote/docs)',
    RECEIVED: 'Received reply',
    OTHER: 'Other',
  }[o] || o || '')

  const _outcomeColor = (o) => ({
    NO_ANSWER: 'red',
    LEFT_VOICEMAIL: 'orange',
    SPOKE: 'green',
    SENT: 'blue',
    RECEIVED: 'green',
  }[o] || 'default')

  // ── Computed fields ────────────────────────────────────────────────────────

  const responseTime = lead && lead.sent_to_client_at
    ? `${Math.round((new Date(lead.sent_to_client_at) - new Date(lead.created_at)) / 3600000)}h`
    : null

  return (
    <>
    <Drawer
      title={
        createMode ? (
          <Text strong style={{ fontSize: 15 }}>Add New Lead</Text>
        ) : (
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
        )
      }
      placement="right" width={560}
      open={open} onClose={onClose}
      extra={
        canWrite ? (
          <Space>
            {!createMode && lead && (
              <Button size="small" icon={<RobotOutlined />} loading={draftLoading} onClick={handleDraftReply}>
                AI Draft
              </Button>
            )}
            <Button onClick={onClose}>Cancel</Button>
            {createMode
              ? <Button type="primary" loading={saving} onClick={handleCreate}>Create Lead</Button>
              : <Button type="primary" loading={saving} onClick={handleSave}>Save Changes</Button>}
          </Space>
        ) : (
          <Button onClick={onClose}>Close</Button>
        )
      }
    >
      {createMode ? (
        <div>
          <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
            Source
          </Title>
          <Select
            style={{ width: '100%', marginBottom: 8 }}
            value={createSource}
            onChange={v => setCreateSource(v)}
          >
            {(sources.length ? sources : SOURCE_OPTIONS.map(c => ({ code: c, name: c }))).map(s => <Select.Option key={s.code} value={s.code}>{s.name}</Select.Option>)}
          </Select>
          <Input
            value={createSourceDetail}
            onChange={e => setCreateSourceDetail(e.target.value)}
            placeholder="Source detail (e.g. Homepage Quote Form, Facebook Ad, Phone call)"
            style={{ marginBottom: 16 }}
          />

          <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
            Contact Information
          </Title>
          <Input value={companyName} onChange={e => setCompanyName(e.target.value)}
            placeholder="Company name" style={{ marginBottom: 8 }} />
          <Input value={contactName} onChange={e => setContactName(e.target.value)}
            placeholder="Contact person" style={{ marginBottom: 8 }} />
          <Input value={contactEmail} onChange={e => setContactEmail(e.target.value)}
            placeholder="Email (e.g. name@company.co.za)" style={{ marginBottom: 8 }} />
          <Input.Group compact style={{ marginBottom: 8, display: 'flex' }}>
            <Select
              value={countryCode}
              onChange={setCountryCode}
              style={{ width: 90 }}
              placeholder="Code"
            >
              <Select.Option value="+27">🇿🇦 +27</Select.Option>
              <Select.Option value="+1">🇺🇸 +1</Select.Option>
              <Select.Option value="+44">🇬🇧 +44</Select.Option>
              <Select.Option value="+61">🇦🇺 +61</Select.Option>
              <Select.Option value="+64">🇳🇿 +64</Select.Option>
              <Select.Option value="+353">🇮🇪 +353</Select.Option>
              <Select.Option value="+971">🇦🇪 +971</Select.Option>
              <Select.Option value="+91">🇮🇳 +91</Select.Option>
              <Select.Option value="+234">🇳🇬 +234</Select.Option>
              <Select.Option value="+254">🇰🇪 +254</Select.Option>
            </Select>
            <Input
              value={contactPhone}
              onChange={e => setContactPhone(formatPhone(e.target.value))}
              placeholder="082 555 1234"
              style={{ flex: 1 }}
            />
          </Input.Group>
          <Input value={companyWebsite} onChange={e => setCompanyWebsite(e.target.value)}
            placeholder="Company website" style={{ marginBottom: 8 }} />
          <Input value={location} onChange={e => setLocation(e.target.value)}
            placeholder="Location (suburb / city)" style={{ marginBottom: 16 }} />

          <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
            Details
          </Title>
          <Select allowClear placeholder="Lead type" style={{ width: '100%', marginBottom: 8 }}
            value={leadType} onChange={setLeadType}>
            {TYPE_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
          </Select>
          <InputNumber min={0} max={100} placeholder="Quality score (0-100)" style={{ width: '100%', marginBottom: 8 }}
            value={qualityScore} onChange={setQualityScore} />
          <Input.TextArea value={createMessage} onChange={e => setCreateMessage(e.target.value)}
            placeholder="Message / excerpt from the enquiry" rows={2} style={{ marginBottom: 8 }} />
          <Input.TextArea value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Notes" rows={2} />
        </div>
      ) : (
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
          {canWrite ? (
            <>
              <Input
                value={companyName}
                onChange={e => setCompanyName(e.target.value)}
                placeholder="Company name"
                style={{ marginBottom: 8 }}
              />
              <Input
                value={contactName}
                onChange={e => setContactName(e.target.value)}
                placeholder="Contact person"
                style={{ marginBottom: 8 }}
              />
              <Input
                value={contactEmail}
                onChange={e => setContactEmail(e.target.value)}
                placeholder="Email address"
                style={{ marginBottom: 8 }}
              />
              <Input
                value={contactPhone}
                onChange={e => setContactPhone(formatPhone(e.target.value))}
                placeholder="Phone number"
                style={{ marginBottom: 8 }}
              />
              <Input
                value={companyWebsite}
                onChange={e => setCompanyWebsite(e.target.value)}
                placeholder="Website (optional)"
                style={{ marginBottom: 8 }}
              />
              <Descriptions column={1} bordered size="small" style={{ marginTop: 8 }}>
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
            </>
          ) : (
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
          )}

          {/* Attribution: Address + Location + UTM */}
          {(canWrite || lead.location || lead.address || lead.utm_source || lead.utm_medium || lead.utm_campaign || lead.source_detail) && (
            <>
              <Title level={5} style={{ margin: '12px 0 8px', fontSize: 13, color: '#555' }}>
                Attribution
              </Title>
              {canWrite && (
                <Input
                  value={address}
                  onChange={e => setAddress(e.target.value)}
                  placeholder="Full address (if confirmed) — e.g. 12 Main Rd, Sandton, 2196"
                  style={{ marginBottom: 8 }}
                />
              )}
              <Descriptions column={1} bordered size="small">
                {lead.location && <Descriptions.Item label="Location">{lead.location}</Descriptions.Item>}
                {address && !canWrite && <Descriptions.Item label="Address">{lead.address}</Descriptions.Item>}
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
              <Form.Item label="Quality Score (0-100)" style={{ marginBottom: 8 }}>
                <InputNumber min={0} max={100} value={qualityScore} onChange={setQualityScore} style={{ width: '100%' }} placeholder="0-100" />
                <Text type="secondary" style={{ display: 'block', fontSize: 11 }}>0=cold · 40+=warm · 70+=hot</Text>
              </Form.Item>
              <Form.Item label="Location" style={{ marginBottom: 8 }}>
                <Input
                  value={location}
                  onChange={e => setLocation(e.target.value)}
                  placeholder="e.g. Sandton, Johannesburg"
                />
              </Form.Item>
              <Form.Item label="Quote Amount (R)" style={{ marginBottom: 8 }} extra="Enter once a quote is sent to the client">
                <Input
                  type="number"
                  value={quoteAmount ?? ''}
                  onChange={e => setQuoteAmount(e.target.value ? Number(e.target.value) : null)}
                  placeholder="e.g. 25000"
                  prefix="R"
                />
              </Form.Item>
              <Form.Item label="Payment Status" style={{ marginBottom: 8 }} extra="Confirm payment received to proceed with production">
                <Select
                  allowClear
                  placeholder="Select payment status"
                  value={paymentStatus}
                  onChange={setPaymentStatus}
                  style={{ width: '100%' }}
                >
                  <Select.Option value="PENDING"><Tag color="orange">Pending</Tag></Select.Option>
                  <Select.Option value="RECEIVED"><Tag color="green">Received — Proceed to Production</Tag></Select.Option>
                </Select>
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

          {/* ── Sales Rep Assignment ────────────────────────────────────── */}
          <Card size="small" style={{ marginTop: 16, background: '#fafafa' }}>
            <Title level={5} style={{ margin: '0 0 8px', fontSize: 13, color: '#555' }}>
              <UserOutlined /> Sales Rep Assignment
            </Title>
            <Descriptions column={1} size="small" bordered style={{ marginBottom: 8 }}>
              <Descriptions.Item label="Assigned To">
                {lead.assigned_to_name || '—'}
                {lead.assigned_to && <Text type="secondary" style={{ fontSize: 11 }}> · {lead.assigned_to}</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="Follow-ups">
                <Text strong>{lead.follow_up_count || 0}</Text>
                {lead.last_follow_up_at && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {' '}· last {dayjs(lead.last_follow_up_at).format('MMM D, HH:mm')}
                  </Text>
                )}
              </Descriptions.Item>
            </Descriptions>
            {canWrite && (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space.Compact style={{ width: '100%' }}>
                  <Select
                    value={assignEmail}
                    onChange={(v) => {
                      setAssignEmail(v)
                      const rep = REP_OPTIONS.find(r => r.email === v)
                      setAssignName(rep ? rep.name.split(' (')[0] : v)
                    }}
                    placeholder="Assign to sales rep"
                    style={{ flex: 1 }}
                  >
                    {REP_OPTIONS.map(r => (
                      <Select.Option key={r.email} value={r.email}>{r.name}</Select.Option>
                    ))}
                  </Select>
                  <Button type="primary" onClick={handleAssign} loading={savingAssign}>
                    Assign
                  </Button>
                </Space.Compact>
                <Space.Compact style={{ width: '100%', marginTop: 8 }}>
                  <Select
                    value={followUpType}
                    onChange={setFollowUpType}
                    style={{ width: '45%' }}
                    options={[
                      { value: 'CALL', label: '📞 Call' },
                      { value: 'EMAIL', label: '✉️ Email' },
                      { value: 'WHATSAPP', label: '💬 WhatsApp' },
                      { value: 'SMS', label: '📱 SMS' },
                      { value: 'NOTE', label: '📝 Note' },
                      { value: 'OTHER', label: 'Other' },
                    ]}
                  />
                  <Select
                    value={followUpOutcome}
                    onChange={setFollowUpOutcome}
                    allowClear
                    placeholder="Outcome (optional)"
                    style={{ width: '55%' }}
                    options={[
                      { value: 'NO_ANSWER', label: '❌ No answer' },
                      { value: 'LEFT_VOICEMAIL', label: '📲 Left voicemail' },
                      { value: 'SPOKE', label: '✅ Spoke to client' },
                      { value: 'SENT', label: '📤 Sent (quote/docs)' },
                      { value: 'RECEIVED', label: '📥 Received reply' },
                      { value: 'OTHER', label: 'Other' },
                    ]}
                  />
                </Space.Compact>
                <Input.TextArea
                  value={followUpNote}
                  onChange={e => setFollowUpNote(e.target.value)}
                  rows={2}
                  placeholder="Log a follow-up... e.g. 'Called client, arranging site visit for Thursday'"
                />
                <Button
                  onClick={handleLogFollowUp}
                  loading={savingFollowUp}
                  icon={<CheckCircleOutlined />}
                  block
                >
                  Log Follow-up
                </Button>
              </Space>
            )}
          </Card>
        </TabPane>

        <TabPane tab={<span><PaperClipOutlined /> Documents <Badge count={documents.length} size="small" style={{ marginLeft: 4 }} /></span>} key="documents">
          {canWrite && (
            <Space direction="vertical" style={{ width: '100%', marginBottom: 12 }}>
              <Space.Compact style={{ width: '100%' }}>
                <Select value={docCategory} onChange={setDocCategory} style={{ width: 140 }}>
                  <Select.Option value="EMAIL">Email</Select.Option>
                  <Select.Option value="QUOTE">Quote</Select.Option>
                  <Select.Option value="RESPONSE">Response</Select.Option>
                  <Select.Option value="OTHER">Other</Select.Option>
                </Select>
                <input
                  type="file"
                  id={`file-upload-${lead.id}`}
                  style={{ display: 'none' }}
                  onChange={async (e) => {
                    const file = e.target.files && e.target.files[0]
                    if (!file) return
                    setUploading(true)
                    try {
                      await api.uploadDocument(lead.id, file, docCategory)
                      message.success('Document uploaded')
                      const res = await api.listDocuments(lead.id)
                      setDocuments(res.documents || [])
                    } catch (err) {
                      message.error(err.message || 'Upload failed')
                    } finally {
                      setUploading(false)
                      e.target.value = ''
                    }
                  }}
                />
                <Button
                  icon={<UploadOutlined />}
                  loading={uploading}
                  onClick={() => document.getElementById(`file-upload-${lead.id}`).click()}
                  style={{ flex: 1 }}
                >
                  {uploading ? 'Uploading...' : 'Upload Document'}
                </Button>
              </Space.Compact>
              <Text type="secondary" style={{ fontSize: 11 }}>Attach response emails, quotes sent, or other files (max 25 MB).</Text>
            </Space>
          )}
          {loadingDocs ? (
            <Spin style={{ display: 'block', marginTop: 40 }} />
          ) : documents.length === 0 ? (
            <Empty description="No documents attached yet" style={{ marginTop: 40 }} />
          ) : (
            <div>
              {documents.map(doc => (
                <div key={doc.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  border: '1px solid #f0f0f0', borderRadius: 6, padding: '8px 12px', marginBottom: 8
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {doc.filename}
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {doc.category} · {doc.size > 0 ? `${(doc.size / 1024).toFixed(0)} KB` : ''}
                      {' '}· {doc.uploaded_by || ''} · {dayjs(doc.created_at).format('MMM D, YYYY HH:mm')}
                    </Text>
                  </div>
                  <Space>
                    <Button
                      size="small" type="link" icon={<DownloadOutlined />}
                      onClick={() => handleDownloadDoc(doc)}
                    >Open</Button>
                    {canWrite && (
                      <Button
                        size="small" type="text" danger icon={<DeleteOutlined />}
                        onClick={async () => {
                          try {
                            await api.deleteDocument(lead.id, doc.id)
                            message.success('Document deleted')
                            const res = await api.listDocuments(lead.id)
                            setDocuments(res.documents || [])
                          } catch (err) {
                            message.error('Delete failed: ' + err.message)
                          }
                        }}
                      />
                    )}
                  </Space>
                </div>
              ))}
            </div>
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

        <TabPane tab={
          <span><CheckCircleOutlined /> Follow-ups <Badge count={activities.length} size="small" style={{ marginLeft: 6 }} /></span>
        } key="followups">
          {loadingActivities ? (
            <Spin style={{ display: 'block', marginTop: 40 }} />
          ) : activities.length === 0 ? (
            <Empty description="No follow-ups logged yet" style={{ marginTop: 40 }} />
          ) : (
            <Timeline
              style={{ marginTop: 16 }}
              items={activities.slice().reverse().map(a => ({
                key: a.id,
                color: a.outcome === 'SPOKE' || a.outcome === 'SENT' || a.outcome === 'RECEIVED' ? 'green' : '#1677ff',
                children: (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Text strong style={{ fontSize: 13 }}>{_activityTypeLabel(a.activity_type)}</Text>
                      {a.outcome && <Tag color={_outcomeColor(a.outcome)}>{_outcomeLabel(a.outcome)}</Tag>}
                    </div>
                    {a.note && <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>{a.note}</div>}
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {dayjs(a.occurred_at || a.created_at).format('MMM D, YYYY HH:mm')}
                      {a.created_by ? ` · ${a.created_by}` : ''}
                    </Text>
                  </div>
                ),
              }))}
            />
          )}
        </TabPane>

        <TabPane tab={
          <span><ClockCircleOutlined /> Reminders <Badge count={reminders.filter(r => r.status === 'PENDING').length} size="small" style={{ marginLeft: 6 }} /></span>
        } key="reminders">
          {canWrite && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>Schedule a reminder</Text>
              <Space.Compact style={{ width: '100%', marginTop: 8 }}>
                <DatePicker
                  value={remindDate}
                  onChange={setRemindDate}
                  style={{ width: '50%' }}
                  placeholder="Date"
                />
                <TimePicker
                  value={remindTime}
                  onChange={setRemindTime}
                  format="HH:mm"
                  style={{ width: '50%' }}
                  placeholder="Time"
                />
              </Space.Compact>
              <Input.TextArea
                value={remindNote}
                onChange={e => setRemindNote(e.target.value)}
                placeholder="Reminder note (e.g. Call client to confirm quote)"
                rows={2}
                style={{ marginTop: 8 }}
              />
              <Button
                type="primary"
                icon={<ClockCircleOutlined />}
                loading={savingReminder}
                onClick={handleScheduleReminder}
                style={{ marginTop: 8, width: '100%' }}
              >
                Schedule Reminder
              </Button>
              <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 4 }}>
                You'll get an email notification at the scheduled time.
              </Text>
            </div>
          )}
          {loadingReminders ? (
            <Spin style={{ display: 'block', marginTop: 20 }} />
          ) : reminders.length === 0 ? (
            <Empty description="No reminders scheduled" style={{ marginTop: 20 }} />
          ) : (
            <div>
              {reminders.map(r => (
                <div key={r.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  border: '1px solid #f0f0f0', borderRadius: 6, padding: '8px 12px', marginBottom: 8
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>
                      {dayjs(r.remind_at).format('MMM D, YYYY HH:mm')}
                      {' '}
                      <Tag color={r.status === 'PENDING' ? 'orange' : r.status === 'SENT' ? 'green' : 'default'}>
                        {r.status}
                      </Tag>
                    </div>
                    {r.note && <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>{r.note}</div>}
                    <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                      by {r.created_by || '—'}
                    </div>
                  </div>
                  {r.status === 'PENDING' && canWrite && (
                    <Button size="small" onClick={() => handleDismissReminder(r.id)}>
                      Dismiss
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </TabPane>
        <TabPane tab={
          <span><MailOutlined /> Notifications <Badge count={emails.length} size="small" style={{ marginLeft: 6 }} /></span>
        } key="notifications">
          {loadingEmails ? (
            <Spin style={{ display: 'block', marginTop: 20 }} />
          ) : emails.length === 0 ? (
            <Empty description="No notifications/emails recorded for this lead" style={{ marginTop: 20 }} />
          ) : (
            <div>
              {emails.map(e => (
                <div key={e.id} style={{
                  border: '1px solid #f0f0f0', borderRadius: 6, padding: '10px 12px', marginBottom: 8
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <div style={{ fontWeight: 500, fontSize: 13, flex: 1, minWidth: 0 }}>
                      {e.subject || '(no subject)'}
                    </div>
                    <Tag color={e.status === 'SENT' ? 'green' : e.status === 'FAILED' ? 'red' : 'default'}>
                      {e.status || '—'}
                    </Tag>
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                    <span>
                      <b>Type:</b>{' '}
                      <Tag style={{ marginRight: 0 }}>{_notificationTypeLabel(e.notification_type)}</Tag>
                    </span>
                    <span><b>To:</b> {e.to_email || '—'}</span>
                    <span><b>From:</b> {e.from_email || '—'}</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                    {e.sent_at ? dayjs(e.sent_at).format('MMM D, YYYY HH:mm') : '—'}
                    {e.direction ? ` · ${e.direction}` : ''}
                    {e.message_id ? ` · ID: ${e.message_id}` : ''}
                  </div>
                  {e.status === 'FAILED' && e.body && (
                    <div style={{ fontSize: 11, color: '#c0392b', marginTop: 4, background: '#fdf0ef', borderRadius: 4, padding: '6px 8px' }}>
                      <b>Error:</b> {e.body.slice(0, 300)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 8 }}>
            Automated notification emails sent for this lead (new lead, allocation, hot-lead alerts).
            Does not affect follow-up status.
          </Text>
        </TabPane>
      </Tabs>
      )}
    </Drawer>

    {/* AI Draft modal */}
    <Modal
      title="🤖 AI Draft Reply"
      open={draftModalOpen}
      onCancel={() => setDraftModalOpen(false)}
      footer={
        <Space>
          <Button onClick={() => setDraftModalOpen(false)}>Close</Button>
          <Button
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(draft || '')
              message.success('Draft copied — paste into your email/WhatsApp')
            }}
          >
            Copy Draft
          </Button>
        </Space>
      }
      width={560}
    >
      {draftError && <Alert type="warning" showIcon message={draftError} style={{ marginBottom: 12 }} />}
      <Input.TextArea
        value={draft || ''}
        onChange={e => setDraft(e.target.value)}
        rows={12}
        placeholder="AI draft will appear here. Review and edit before sending."
      />
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
        AI-generated draft — always review before sending. You can edit this text freely.
      </Text>
    </Modal>
    </>
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
  const [tallyOpen, setTallyOpen] = useState(false)
  const [tallyCampaign, setTallyCampaign] = useState(null)
  const [savingTally, setSavingTally] = useState(false)
  const [compOpen, setCompOpen] = useState(false)
  const [compData, setCompData] = useState([])
  const [compLoading, setCompLoading] = useState(false)
  const [tallyForm] = Form.useForm()
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
      location: camp.location || '',
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

  const openTally = (camp) => {
    setTallyCampaign(camp)
    tallyForm.resetFields()
    tallyForm.setFieldsValue({ log_date: dayjs(), cards_given: 0, people_stopped: 0 })
    setTallyOpen(true)
  }

  const handleLogTally = async (values) => {
    setSavingTally(true)
    try {
      await api.logDailyTally(tallyCampaign.id, {
        log_date: values.log_date ? values.log_date.toISOString() : undefined,
        cards_given: values.cards_given || 0,
        people_stopped: values.people_stopped || 0,
      })
      message.success('Daily tally logged')
      setTallyOpen(false)
      load()
    } catch (e) {
      message.error('Failed to log tally: ' + e.message)
    } finally {
      setSavingTally(false)
    }
  }

  const openComparison = async () => {
    setCompOpen(true)
    setCompLoading(true)
    try {
      const res = await api.roadsideComparison(clientId)
      setCompData(res.campaigns || [])
    } catch (e) {
      message.error('Failed to load comparison: ' + e.message)
    } finally {
      setCompLoading(false)
    }
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
    { title: 'Cards', dataIndex: 'total_cards', align: 'right', width: 80, render: v => v || 0 },
    { title: 'Stopped', dataIndex: 'total_people', align: 'right', width: 80, render: v => v || 0 },
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
          {canWrite && r.channel === 'ROADSIDE' && (
            <Button size="small" icon={<FieldTimeOutlined />} onClick={() => openTally(r)}>Log Tally</Button>
          )}
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
        <Space>
          {canWrite && (
            <Button icon={<BarChartOutlined />} onClick={openComparison}>
              Roadside Comparison
            </Button>
          )}
          {canWrite && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              New Campaign
            </Button>
          )}
        </Space>
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
          <Form.Item name="location" label="Location / Area">
            <Input placeholder="e.g. Sandton, Fourways (for roadside activations)" />
          </Form.Item>
          <Form.Item name="status" label="Status">
            <Select>
              {CAMPAIGN_STATUS_OPTIONS.map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* Daily Tally Modal */}
      <Modal
        title={`Log Daily Tally — ${tallyCampaign ? tallyCampaign.name : ''}`}
        open={tallyOpen}
        onCancel={() => setTallyOpen(false)}
        onOk={() => tallyForm.submit()}
        confirmLoading={savingTally}
        okText="Log Tally"
        destroyOnClose
      >
        <Form form={tallyForm} layout="vertical" onFinish={handleLogTally} style={{ marginTop: 16 }}>
          <Form.Item name="log_date" label="Date" rules={[{ required: true, message: 'Date is required' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cards_given" label="Business Cards Handed Out" rules={[{ required: true, message: 'Enter cards given' }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="people_stopped" label="People Who Stopped to View" rules={[{ required: true, message: 'Enter people stopped' }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Roadside Comparison Modal */}
      <Modal
        title="📊 Roadside Marketing Comparison"
        open={compOpen}
        onCancel={() => setCompOpen(false)}
        footer={<Button onClick={() => setCompOpen(false)}>Close</Button>}
        width={820}
      >
        {compLoading ? (
          <Spin style={{ display: 'block', margin: 40 }} />
        ) : compData.length === 0 ? (
          <Empty description="No roadside campaigns yet. Create ROADSIDE campaigns and log daily tallies to compare sites." />
        ) : (
          <Table
            dataSource={compData}
            rowKey="id"
            size="small"
            pagination={false}
            columns={[
              { title: 'Site / Area', dataIndex: 'location', render: (v, r) => <Text strong>{v || r.name}</Text> },
              { title: 'Campaign', dataIndex: 'name' },
              { title: 'Status', dataIndex: 'status', render: s => <CampaignStatusTag status={s} /> },
              { title: 'Cards', dataIndex: 'total_cards', align: 'right', render: v => <Text strong>{v || 0}</Text> },
              { title: 'Stopped', dataIndex: 'total_people', align: 'right', render: v => <Text strong>{v || 0}</Text> },
              { title: 'Leads', dataIndex: 'lead_count', align: 'right' },
              { title: 'Qualified', dataIndex: 'qualified_count', align: 'right' },
              { title: 'Converted', dataIndex: 'converted_count', align: 'right' },
              {
                title: 'Conv Rate',
                align: 'right',
                render: (_, r) => r.lead_count > 0
                  ? <Text strong>{Math.round(r.converted_count / r.lead_count * 100)}%</Text>
                  : <Text type="secondary">—</Text>,
              },
            ]}
          />
        )}
      </Modal>

      {/* Partner Hand-off Modal */}
      <Modal
        title="🤝 Hand Lead to Partner"
        open={!!handoffLead}
        onCancel={() => setHandoffLead(null)}
        footer={
          <Space>
            <Button onClick={() => setHandoffLead(null)}>Cancel</Button>
            <Button type="primary" loading={handoffSaving} onClick={doHandoff} icon={<SendOutlined />}>
              Hand to Partner
            </Button>
          </Space>
        }
      >
        {handoffLead && (
          <div>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={`Handing off: ${handoffLead.company_name || handoffLead.contact_name || handoffLead.contact_email || 'Untitled lead'}`}
              description="This creates a copy of the lead under the partner client. The original stays in your records for tracking."
            />
            <div style={{ marginBottom: 12 }}>
              <Text strong>Partner Client</Text>
              <Select
                style={{ width: '100%', marginTop: 4 }}
                placeholder="Select partner client"
                value={handoffClientId}
                onChange={onHandoffClientChange}
                options={(handoffClients || []).map(c => ({ value: c.id, label: c.company_name }))}
              />
            </div>
            <div>
              <Text strong>Assign To</Text>
              <Select
                style={{ width: '100%', marginTop: 4 }}
                placeholder="Select user"
                value={handoffTargetEmail}
                onChange={setHandoffTargetEmail}
                disabled={!handoffClientId}
                options={(handoffTargets || []).map(u => ({ value: u.email, label: `${u.full_name || u.email} (${u.email})` }))}
              />
            </div>
          </div>
        )}
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
  const [resetTarget, setResetTarget] = useState(null)
  const [resetForm] = Form.useForm()

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
      await api.createUser({ ...values, send_welcome: !!values.send_welcome })
      message.success(values.send_welcome
        ? 'User created — login details emailed'
        : 'User created')
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

  const handleResetPassword = async (values) => {
    if (!resetTarget) return
    try {
      await api.resetPassword(resetTarget.id, values.new_password)
      message.success(`Password reset — temp password emailed to ${resetTarget.email}`)
      setResetTarget(null)
      resetForm.resetFields()
    } catch (e) {
      message.error('Failed to reset password: ' + e.message)
    }
  }

  const columns = [
    { title: 'Name', dataIndex: 'full_name', render: v => <Text strong>{v}</Text> },
    { title: 'Email', dataIndex: 'email', render: v => <Text code style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: 'Role',
      dataIndex: 'role',
      render: r => <Tag color={r === 'SYSTEM_ADMIN' ? 'red' : r === 'CLIENT_ADMIN' ? 'blue' : r === 'AGENT' ? 'purple' : 'default'}>{r}</Tag>,
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
          <Space size={4} wrap>
            <Button size="small" icon={<KeyOutlined />} onClick={() => { setResetTarget(r); resetForm.setFieldsValue({ new_password: '' }) }}>
              Reset PW
            </Button>
            <Button size="small" danger onClick={() => handleDelete(r.id, r.email)}>
              Disable
            </Button>
          </Space>
        )
      ),
      width: 170,
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
              <Select.Option value="AGENT">AGENT — Sales rep, sees only their assigned leads</Select.Option>
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
          <Form.Item name="send_welcome" valuePropName="checked" style={{ marginBottom: 8 }}>
            <Checkbox>Email login details to this user (site, email, temporary password)</Checkbox>
          </Form.Item>
          <Button type="primary" htmlType="submit" block>Create User</Button>
        </Form>
      </Modal>

      <Modal
        title={resetTarget ? `Reset Password — ${resetTarget.full_name}` : 'Reset Password'}
        open={!!resetTarget}
        onCancel={() => { setResetTarget(null); resetForm.resetFields() }}
        footer={null}
        destroyOnClose
      >
        <Form form={resetForm} layout="vertical" onFinish={handleResetPassword} style={{ marginTop: 16 }}>
          {resetTarget && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={`Set a temporary password for ${resetTarget.email}`}
              description="The user will be emailed this temporary password and must change it on next login."
            />
          )}
          <Form.Item name="new_password" label="Temporary Password" rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder="Min 8 characters" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block icon={<KeyOutlined />}>
            Reset & Email Password
          </Button>
        </Form>
      </Modal>
    </div>
  )
}

// ── Clients Tab (SYSTEM_ADMIN only) ─────────────────────────────────────────────

function ClientsTab({ onClientAdded }) {
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const cs = await api.listClients()
      setClients(cs)
    } catch (e) {
      message.error('Failed to load clients: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleOnboard = async (values) => {
    setSubmitting(true)
    try {
      const res = await api.onboardClient(values)
      setResult(res)
      await load()
      if (onClientAdded) onClientAdded()
    } catch (e) {
      message.error('Onboarding failed: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const closeModal = () => {
    setModalOpen(false)
    setResult(null)
    form.resetFields()
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          Onboard New Client
        </Button>
        <Text type="secondary">{clients.length} client{clients.length === 1 ? '' : 's'}</Text>
      </Space>

      <Table
        dataSource={clients}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={false}
        columns={[
          { title: 'Company', dataIndex: 'company_name' },
          { title: 'Contact Email', dataIndex: 'contact_email' },
          { title: 'API Key', dataIndex: 'api_key', render: k => k ? <Text code style={{ fontSize: 11 }}>{k.slice(0, 12)}…</Text> : '—' },
          { title: 'Created', dataIndex: 'created_at', render: d => d ? dayjs(d).format('DD MMM YYYY') : '—' },
        ]}
      />

      <Modal
        title={result ? 'Client Onboarded ✅' : 'Onboard New Client'}
        open={modalOpen}
        onCancel={closeModal}
        footer={result ? (
          <Button type="primary" onClick={closeModal}>Done</Button>
        ) : (
          <>
            <Button onClick={closeModal}>Cancel</Button>
            <Button type="primary" loading={submitting} onClick={() => form.submit()}>
              Onboard Client
            </Button>
          </>
        )}
        width={result ? 520 : 480}
      >
        {result ? (
          <div>
            <p style={{ marginBottom: 12 }}>Client <strong>{result.client.company_name}</strong> is ready. Share these credentials with the client admin:</p>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Client ID"><Text code>{result.client.id}</Text></Descriptions.Item>
              <Descriptions.Item label="API Key"><Text code copyable>{result.api_key}</Text></Descriptions.Item>
              <Descriptions.Item label="Admin Login"><Text code>{result.admin_user.email}</Text></Descriptions.Item>
              <Descriptions.Item label="Admin Password"><Text code copyable>{result.admin_password || '—'}</Text></Descriptions.Item>
              <Descriptions.Item label="Campaign">{result.campaign.name}</Descriptions.Item>
            </Descriptions>
            <p style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
              The admin can log in at the portal URL and use the API key for the public lead capture endpoint.
            </p>
          </div>
        ) : (
          <Form form={form} layout="vertical" onFinish={handleOnboard}>
            <Form.Item name="company_name" label="Company Name" rules={[{ required: true }]}>
              <Input placeholder="e.g. Acme Renovations" />
            </Form.Item>
            <Form.Item name="contact_email" label="Contact Email" rules={[{ required: true, type: 'email' }]}>
              <Input placeholder="contact@company.com" />
            </Form.Item>
            <Form.Item name="admin_email" label="Admin Email" rules={[{ required: true, type: 'email' }]}>
              <Input placeholder="admin@company.com" />
            </Form.Item>
            <Form.Item name="admin_password" label="Admin Password" rules={[{ required: true, min: 8 }]}>
              <Input.Password placeholder="Set a strong password" />
            </Form.Item>
            <Form.Item name="admin_full_name" label="Admin Full Name">
              <Input placeholder="e.g. Jane Doe" />
            </Form.Item>
            <Form.Item name="campaign_name" label="Default Campaign Name">
              <Input placeholder="e.g. Acme-Q3-Outreach (optional)" />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  )
}

// ── Sources Tab (SYSTEM_ADMIN only) ───────────────────────────────────────────

function SourcesTab({ sources, onSourcesChange }) {
  const [allSources, setAllSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.listAllSources()
      setAllSources(res || [])
      onSourcesChange && onSourcesChange((res || []).filter(s => s.is_active === 1))
    } catch (e) {
      message.error('Failed to load sources: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (values) => {
    try {
      await api.createSource({ code: values.code, name: values.name, sort_order: 0 })
      message.success('Source added')
      setModalOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error('Failed to add source: ' + e.message)
    }
  }

  const handleToggle = async (src) => {
    try {
      await api.updateSource(src.id, { is_active: src.is_active === 1 ? 0 : 1 })
      message.success(src.is_active === 1 ? 'Source deactivated' : 'Source activated')
      load()
    } catch (e) {
      message.error('Failed: ' + e.message)
    }
  }

  const columns = [
    { title: 'Code', dataIndex: 'code', width: 180, render: c => <Text code>{c}</Text> },
    { title: 'Name', dataIndex: 'name' },
    { title: 'Order', dataIndex: 'sort_order', width: 80, align: 'center' },
    {
      title: 'Status',
      width: 100,
      align: 'center',
      render: (_, r) => <Tag color={r.is_active === 1 ? 'green' : 'default'}>{r.is_active === 1 ? 'Active' : 'Inactive'}</Tag>,
    },
    {
      title: '',
      width: 160,
      render: (_, r) => (
        <Space size="small">
          <Button size="small" onClick={() => handleToggle(r)}>
            {r.is_active === 1 ? 'Deactivate' : 'Activate'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Manage lead source values. Sources are tracked for reporting — deactivating hides them from dropdowns but keeps existing leads intact.
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          Add Source
        </Button>
      </div>

      <Table
        dataSource={allSources}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={false}
      />

      <Modal title="Add Source" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null}>
        <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item name="code" label="Code" rules={[{ required: true, message: 'Code is required' }]}
            extra="Uppercase short code, e.g. LINKEDIN, EXPO, REFERRAL">
            <Input placeholder="e.g. LINKEDIN" />
          </Form.Item>
          <Form.Item name="name" label="Display name" rules={[{ required: true, message: 'Name is required' }]}>
            <Input placeholder="e.g. LinkedIn" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>Add Source</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ── Scoring Rules Tab (SYSTEM_ADMIN only) ──────────────────────────────────────

const SCORE_FIELDS = [
  { value: 'source', label: 'Source' },
  { value: 'has_phone', label: 'Has Phone' },
  { value: 'has_website', label: 'Has Website' },
  { value: 'has_email', label: 'Has Email' },
  { value: 'no_email', label: 'No Email' },
  { value: 'lead_type', label: 'Lead Type' },
  { value: 'location', label: 'Location' },
  { value: 'message_keyword', label: 'Message Keyword' },
  { value: 'age_days', label: 'Age (days)' },
]

const SCORE_OPERATORS = [
  { value: 'eq', label: 'equals' },
  { value: 'ne', label: 'not equals' },
  { value: 'contains', label: 'contains' },
  { value: 'is_true', label: 'is true' },
  { value: 'is_false', label: 'is false' },
  { value: 'gt', label: 'greater than' },
  { value: 'lt', label: 'less than' },
]

function ScoringRulesTab() {
  const [rules, setRules] = useState([])
  const [tiers, setTiers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [r, t] = await Promise.all([api.listScoringRules(), api.getScoringTiers()])
      setRules(r || [])
      setTiers(t)
    } catch (e) {
      message.error('Failed to load scoring rules: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (values) => {
    try {
      await api.createScoringRule({
        field: values.field,
        operator: values.operator,
        value: values.value || null,
        points: values.points,
        client_id: null,
      })
      message.success('Rule added')
      setModalOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error('Failed to add rule: ' + e.message)
    }
  }

  const handleToggle = async (rule) => {
    try {
      await api.updateScoringRule(rule.id, { is_active: rule.is_active === 1 ? 0 : 1 })
      message.success(rule.is_active === 1 ? 'Rule deactivated' : 'Rule activated')
      load()
    } catch (e) {
      message.error('Failed: ' + e.message)
    }
  }

  const fieldLabel = (f) => (SCORE_FIELDS.find(x => x.value === f) || {}).label || f
  const opLabel = (o) => (SCORE_OPERATORS.find(x => x.value === o) || {}).label || o

  const columns = [
    { title: 'Field', dataIndex: 'field', width: 150, render: f => <Text strong>{fieldLabel(f)}</Text> },
    { title: 'Condition', dataIndex: 'operator', width: 130, render: (o, r) => <Text>{opLabel(o)}{r.value ? ` "${r.value}"` : ''}</Text> },
    { title: 'Points', dataIndex: 'points', width: 80, align: 'center', render: p => <Tag color={p >= 0 ? 'green' : 'red'}>{p >= 0 ? `+${p}` : p}</Tag> },
    { title: 'Scope', dataIndex: 'client_id', width: 90, render: c => c ? 'Client' : 'Global' },
    { title: 'Status', width: 90, align: 'center', render: (_, r) => <Tag color={r.is_active === 1 ? 'green' : 'default'}>{r.is_active === 1 ? 'Active' : 'Off'}</Tag> },
    { title: '', width: 120, render: (_, r) => <Button size="small" onClick={() => handleToggle(r)}>{r.is_active === 1 ? 'Deactivate' : 'Activate'}</Button> },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Auto-score leads (0-100) from rules. Scores recalculate on every lead create/update.
          </Text>
          {tiers && (
            <div style={{ marginTop: 8 }}>
              <Tag color="red">🔥 Hot: {tiers.hot}</Tag>
              <Tag color="orange">Warm: {tiers.warm}</Tag>
              <Tag color="default">Cold: {tiers.cold}</Tag>
              <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>Hot ≥ 70 · Warm 40-69 · Cold &lt; 40</Text>
            </div>
          )}
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          Add Rule
        </Button>
      </div>

      <Table
        dataSource={rules}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={false}
      />

      <Modal title="Add Scoring Rule" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null}>
        <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item name="field" label="Field" rules={[{ required: true }]}>
            <Select placeholder="Select field">
              {SCORE_FIELDS.map(f => <Select.Option key={f.value} value={f.value}>{f.label}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="operator" label="Condition" rules={[{ required: true }]} initialValue="eq">
            <Select>
              {SCORE_OPERATORS.map(o => <Select.Option key={o.value} value={o.value}>{o.label}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="value" label="Value (for equals/contains/greater-than)">
            <Input placeholder="e.g. HARO, quote, 7" />
          </Form.Item>
          <Form.Item name="points" label="Points (positive adds, negative subtracts)" rules={[{ required: true }]}>
            <Input type="number" placeholder="e.g. 10 or -5" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>Add Rule</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ── Reports Tab ─────────────────────────────────────────────────────────────────

function ReportsTab({ clientId }) {
  const [agent, setAgent] = useState(null)
  const [pipeline, setPipeline] = useState(null)
  const [funnel, setFunnel] = useState(null)
  const [roi, setRoi] = useState(null)
  const [responseTime, setResponseTime] = useState(null)
  const [activity, setActivity] = useState(null)
  const [funnelTrend, setFunnelTrend] = useState(null)
  const [trendBucket, setTrendBucket] = useState('week')
  const [overdue, setOverdue] = useState(null)
  const [campaigns, setCampaigns] = useState(null)
  const [winLoss, setWinLoss] = useState(null)
  const [loading, setLoading] = useState(true)
  const [preset, setPreset] = useState('commission')
  const [dateFrom, setDateFrom] = useState(null)
  const [dateTo, setDateTo] = useState(null)

  // Default: commission window (1st-21st of current month) — cut-off 21st, payouts 25th
  useEffect(() => {
    const now = new Date()
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
    const c21 = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-21`
    setDateFrom(first)
    setDateTo(c21)
  }, [])

  const applyPreset = (p) => {
    const now = new Date()
    const y = now.getFullYear()
    const m = now.getMonth()
    const pad = (n) => String(n).padStart(2, '0')
    if (p === 'commission') {
      setDateFrom(`${y}-${pad(m + 1)}-01`)
      setDateTo(`${y}-${pad(m + 1)}-21`)
    } else if (p === 'lastMonth') {
      const ly = m === 0 ? y - 1 : y
      const lm = m === 0 ? 12 : m
      setDateFrom(`${ly}-${pad(lm)}-01`)
      setDateTo(`${ly}-${pad(lm)}-28`)
    } else if (p === 'all') {
      setDateFrom(null)
      setDateTo(null)
    }
    setPreset(p)
  }

  const load = async () => {
    setLoading(true)
    try {
      const qs = new URLSearchParams()
      if (clientId) qs.set('client_id', clientId)
      if (dateFrom) qs.set('date_from', dateFrom)
      if (dateTo) qs.set('date_to', dateTo)
      const q = qs.toString()
      const [a, p, f, r, rt, act, ft, od, cg, wl] = await Promise.all([
        api.agentSalesReport(clientId, dateFrom, dateTo),
        api.pipelineReport(clientId, dateFrom, dateTo),
        api.funnelReport(clientId, dateFrom, dateTo),
        api.sourceRoiReport(clientId, dateFrom, dateTo),
        api.responseTimeReport(clientId, dateFrom, dateTo),
        api.activityReport(clientId, dateFrom, dateTo),
        api.funnelTrendReport(clientId, dateFrom, dateTo, trendBucket),
        api.overdueReport(clientId),
        api.campaignPerformanceReport(clientId, dateFrom, dateTo),
        api.winLossReport(clientId, dateFrom, dateTo),
      ])
      setAgent(a)
      setPipeline(p)
      setFunnel(f)
      setRoi(r)
      setResponseTime(rt)
      setActivity(act)
      setFunnelTrend(ft)
      setOverdue(od)
      setCampaigns(cg)
      setWinLoss(wl)
    } catch (e) {
      message.error('Failed to load reports: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [clientId, dateFrom, dateTo, trendBucket])

  const fmt = (n) => 'R' + (n || 0).toLocaleString('en-ZA', { maximumFractionDigits: 0 })

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>

  const agentCols = [
    { title: 'Agent', dataIndex: 'name', render: n => <Text strong>{n}</Text> },
    { title: 'Leads', dataIndex: 'leads', align: 'right', width: 70 },
    { title: 'Quoted', dataIndex: 'quoted', align: 'right', width: 70 },
    { title: 'Won', dataIndex: 'converted', align: 'right', width: 70, render: v => <Tag color="green">{v}</Tag> },
    { title: 'Lost', dataIndex: 'lost', align: 'right', width: 70, render: v => <Tag color="red">{v}</Tag> },
    { title: 'Open', dataIndex: 'open', align: 'right', width: 70 },
    { title: 'Quoted Value', dataIndex: 'quoted_value', align: 'right', render: v => <Text strong style={{ color: '#1677ff' }}>{fmt(v)}</Text> },
    { title: 'Predicted (50%)', dataIndex: 'predicted_value', align: 'right', render: v => <Text strong style={{ color: '#722ed1' }}>{fmt(v)}</Text> },
    { title: 'Won Value', dataIndex: 'won_value', align: 'right', render: v => <Text strong style={{ color: '#52c41a' }}>{fmt(v)}</Text> },
  ]

  const roiCols = [
    { title: 'Source', dataIndex: 'source', render: s => <Text strong>{s?.replace('_', ' ')}</Text> },
    { title: 'Leads', dataIndex: 'leads', align: 'right', width: 70 },
    { title: 'Quoted', dataIndex: 'quoted', align: 'right', width: 70 },
    { title: 'Conv. Rate', dataIndex: 'conversion_rate', align: 'right', width: 90, render: v => <Tag color={v >= 20 ? 'green' : v >= 10 ? 'orange' : 'default'}>{v}%</Tag> },
    { title: 'Quoted Value', dataIndex: 'quoted_value', align: 'right', render: v => <Text strong style={{ color: '#1677ff' }}>{fmt(v)}</Text> },
    { title: 'Won Value', dataIndex: 'won_value', align: 'right', render: v => <Text strong style={{ color: '#52c41a' }}>{fmt(v)}</Text> },
    { title: 'Avg Deal', dataIndex: 'avg_deal_value', align: 'right', render: v => <Text>{fmt(v)}</Text> },
  ]

  // Format a duration in hours into human-readable e.g. '45m', '3h', '2d 4h'
  const fmtHours = (h) => {
    if (h === null || h === undefined) return '—'
    if (h < 1) return Math.round(h * 60) + 'm'
    if (h < 24) return (Math.round(h * 10) / 10) + 'h'
    const d = Math.floor(h / 24)
    const rem = Math.round(h % 24)
    return d + 'd ' + rem + 'h'
  }

  const responseCols = [
    { title: 'Agent', dataIndex: 'name', render: n => <Text strong>{n}</Text> },
    { title: 'Leads', dataIndex: 'leads', align: 'right', width: 70 },
    { title: 'Responded', dataIndex: 'responded', align: 'right', width: 90, render: v => <Tag color="green">{v}</Tag> },
    { title: 'No Response', dataIndex: 'no_response', align: 'right', width: 95, render: v => <Tag color={v > 0 ? 'red' : 'default'}>{v}</Tag> },
    { title: 'Resp. Rate', dataIndex: 'response_rate', align: 'right', width: 85, render: v => <Text strong style={{ color: v >= 80 ? '#52c41a' : v >= 50 ? '#fa8c16' : '#cf1322' }}>{v}%</Text> },
    { title: 'Avg Response', dataIndex: 'avg_response_hours', align: 'right', render: v => <Text strong style={{ color: v !== null && v <= 24 ? '#52c41a' : v !== null && v <= 72 ? '#fa8c16' : v !== null ? '#cf1322' : '#999' }}>{fmtHours(v)}</Text> },
    { title: 'Median', dataIndex: 'median_response_hours', align: 'right', render: v => <Text>{fmtHours(v)}</Text> },
    { title: 'Fastest', dataIndex: 'fastest_response_hours', align: 'right', render: v => <Text>{fmtHours(v)}</Text> },
    { title: 'Slowest', dataIndex: 'slowest_response_hours', align: 'right', render: v => <Text>{fmtHours(v)}</Text> },
  ]

  const ov = responseTime?.overall

  const activityCols = [
    { title: 'Agent', dataIndex: 'name', render: n => <Text strong>{n}</Text> },
    { title: 'Activities', dataIndex: 'total', align: 'right', width: 90, render: v => <Text strong>{v}</Text> },
    { title: 'Leads Worked', dataIndex: 'leads_worked', align: 'right', width: 100 },
    { title: 'Calls', dataIndex: ['by_type', 'CALL'], align: 'right', width: 70, render: v => v || 0 },
    { title: 'Emails', dataIndex: ['by_type', 'EMAIL'], align: 'right', width: 70, render: v => v || 0 },
    { title: 'WhatsApp', dataIndex: ['by_type', 'WHATSAPP'], align: 'right', width: 80, render: v => v || 0 },
    { title: 'SMS', dataIndex: ['by_type', 'SMS'], align: 'right', width: 60, render: v => v || 0 },
    { title: 'Notes', dataIndex: ['by_type', 'NOTE'], align: 'right', width: 60, render: v => v || 0 },
    { title: 'Other', dataIndex: ['by_type', 'OTHER'], align: 'right', width: 60, render: v => v || 0 },
  ]

  const actOv = activity?.overall

  const trendCols = [
    { title: trendBucket === 'month' ? 'Month' : 'Week', dataIndex: 'period', render: p => <Text strong>{p}</Text> },
    { title: 'Leads', dataIndex: 'leads', align: 'right', width: 70 },
    { title: 'Qualified', dataIndex: 'qualified', align: 'right', width: 80 },
    { title: 'Contacted', dataIndex: 'contacted', align: 'right', width: 85 },
    { title: 'Converted', dataIndex: 'converted', align: 'right', width: 85, render: v => <Tag color="green">{v}</Tag> },
    { title: 'Qual. Rate', dataIndex: 'qualification_rate', align: 'right', width: 85, render: v => <Text style={{ color: '#1677ff' }}>{v}%</Text> },
    { title: 'Contact Rate', dataIndex: 'contact_rate', align: 'right', width: 95, render: v => <Text style={{ color: '#722ed1' }}>{v}%</Text> },
    { title: 'Conv. Rate', dataIndex: 'conversion_rate', align: 'right', width: 90, render: v => <Tag color={v >= 20 ? 'green' : v >= 10 ? 'orange' : 'default'}>{v}%</Tag> },
  ]

  const fmtDur = (h) => {
    if (h === null || h === undefined) return '—'
    if (h < 24) return Math.round(h) + 'h'
    return Math.floor(h / 24) + 'd ' + Math.round(h % 24) + 'h'
  }

  const overdueCols = [
    { title: 'Company', dataIndex: 'company', render: c => <Text strong>{c}</Text> },
    { title: 'Contact', dataIndex: 'contact_name', render: c => c || '—' },
    { title: 'Phone', dataIndex: 'contact_phone', render: p => p || '—' },
    { title: 'Agent', dataIndex: 'assigned_to' },
    { title: 'Status', dataIndex: 'status', render: s => <Tag>{s}</Tag> },
    { title: 'Issue', dataIndex: 'issues', render: iss => (iss || []).map(([reason, h]) => <Tag key={reason} color="red" style={{ marginBottom: 2 }}>{reason} · {fmtDur(h)}</Tag>) },
  ]

  const campaignCols = [
    { title: 'Campaign', dataIndex: 'name', render: n => <Text strong>{n}</Text> },
    { title: 'Channel', dataIndex: 'channel', render: c => <Tag>{c?.replace('_', ' ') || '—'}</Tag> },
    { title: 'Location', dataIndex: 'location', render: l => l || '—' },
    { title: 'Leads', dataIndex: 'leads', align: 'right', width: 70 },
    { title: 'Qualified', dataIndex: 'qualified', align: 'right', width: 85 },
    { title: 'Converted', dataIndex: 'converted', align: 'right', width: 85, render: v => <Tag color="green">{v}</Tag> },
    { title: 'Conv. Rate', dataIndex: 'conversion_rate', align: 'right', width: 90, render: v => <Tag color={v >= 20 ? 'green' : v >= 10 ? 'orange' : 'default'}>{v}%</Tag> },
    { title: 'Cards', dataIndex: 'cards_given', align: 'right', width: 70, render: v => v || '—' },
    { title: 'Stopped', dataIndex: 'people_stopped', align: 'right', width: 80, render: v => v || '—' },
  ]

  const wlSum = winLoss?.summary
  const wlSourceCols = [
    { title: 'Source', dataIndex: 'key', render: s => <Text strong>{s?.replace('_', ' ')}</Text> },
    { title: 'Won', dataIndex: 'won', align: 'right', width: 70, render: v => <Tag color="green">{v}</Tag> },
    { title: 'Lost', dataIndex: 'lost', align: 'right', width: 70, render: v => <Tag color="red">{v}</Tag> },
    { title: 'Win Rate', dataIndex: 'win_rate', align: 'right', width: 90, render: v => <Text strong style={{ color: v >= 50 ? '#52c41a' : '#cf1322' }}>{v}%</Text> },
    { title: 'Won Value', dataIndex: 'won_value', align: 'right', render: v => <Text strong style={{ color: '#52c41a' }}>{fmt(v)}</Text> },
  ]
  const wlAgentCols = [
    { title: 'Agent', dataIndex: 'name', render: n => <Text strong>{n}</Text> },
    { title: 'Won', dataIndex: 'won', align: 'right', width: 70, render: v => <Tag color="green">{v}</Tag> },
    { title: 'Lost', dataIndex: 'lost', align: 'right', width: 70, render: v => <Tag color="red">{v}</Tag> },
    { title: 'Win Rate', dataIndex: 'win_rate', align: 'right', width: 90, render: v => <Text strong style={{ color: v >= 50 ? '#52c41a' : '#cf1322' }}>{v}%</Text> },
    { title: 'Won Value', dataIndex: 'won_value', align: 'right', render: v => <Text strong style={{ color: '#52c41a' }}>{fmt(v)}</Text> },
  ]

  return (
    <div>
      {/* Date-range filter */}
      <Space wrap style={{ marginBottom: 16 }}>
        <Segmented
          value={preset}
          onChange={applyPreset}
          options={[
            { label: 'Commission (1-21)', value: 'commission' },
            { label: 'Last Month', value: 'lastMonth' },
            { label: 'All Time', value: 'all' },
          ]}
          size="small"
        />
        <DatePicker.RangePicker
          value={dateFrom && dateTo ? [dayjs(dateFrom), dayjs(dateTo)] : null}
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              setDateFrom(dates[0].format('YYYY-MM-DD'))
              setDateTo(dates[1].format('YYYY-MM-DD'))
            }
          }}
          size="small"
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          Commission cut-off: 21st · Payouts: 25th
        </Text>
      </Space>

      {/* Pipeline value summary */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center', background: '#f0f5ff' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#1677ff' }}>{fmt(pipeline?.quoted_value)}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>Quoted Sales (all quotes)</Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center', background: '#f9f0ff' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#722ed1' }}>{fmt(pipeline?.predicted_value)}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>Predicted Sales ({Math.round((pipeline?.conversion_probability || 0) * 100)}%)</Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center', background: '#f6ffed' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#52c41a' }}>{fmt(pipeline?.won_value)}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>Won Value</Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{pipeline?.total_leads || 0}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>Total Leads</Text>
          </Card>
        </Col>
      </Row>

      <Title level={5} style={{ margin: '8px 0 12px' }}>Agent Sales Report</Title>
      <Table
        dataSource={agent?.agents || []}
        columns={agentCols}
        rowKey="email"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '8px 0 12px' }}>Source ROI</Title>
      <Table
        dataSource={roi?.sources || []}
        columns={roiCols}
        rowKey="source"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '16px 0 4px' }}>Lead Response Time</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        Time from lead creation to first logged contact. Fast response = higher close rate.
      </Text>
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700 }}>{ov?.leads || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Leads</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{fmtHours(ov?.avg_response_hours)}</div><Text type="secondary" style={{ fontSize: 11 }}>Avg Response</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#1677ff' }}>{fmtHours(ov?.median_response_hours)}</div><Text type="secondary" style={{ fontSize: 11 }}>Median Response</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: ov?.response_rate >= 80 ? '#52c41a' : '#cf1322' }}>{ov?.response_rate || 0}%</div><Text type="secondary" style={{ fontSize: 11 }}>Response Rate ({ov?.no_response || 0} no response)</Text></Card>
        </Col>
      </Row>
      <Table
        dataSource={responseTime?.agents || []}
        columns={responseCols}
        rowKey="email"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '16px 0 4px' }}>Activity / Follow-up Volume</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        Follow-up attempts logged per agent (calls, emails, WhatsApp, etc.) — shows effort, not just results.
      </Text>
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={8}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700 }}>{actOv?.total_activities || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Total Activities</Text></Card>
        </Col>
        <Col span={8}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#1677ff' }}>{actOv?.leads_worked || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Leads Worked</Text></Card>
        </Col>
        <Col span={8}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{actOv?.by_type?.CALL || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Calls Logged</Text></Card>
        </Col>
      </Row>
      <Table
        dataSource={activity?.agents || []}
        columns={activityCols}
        rowKey="email"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '16px 0 4px' }}>Conversion Funnel Trend</Title>
      <Space style={{ marginBottom: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>View by:</Text>
        <Segmented
          value={trendBucket}
          onChange={setTrendBucket}
          options={[
            { label: 'Weekly', value: 'week' },
            { label: 'Monthly', value: 'month' },
          ]}
        />
      </Space>
      <Table
        dataSource={funnelTrend?.buckets || []}
        columns={trendCols}
        rowKey="period"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '16px 0 4px' }}>Overdue / Stale Leads</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        Open leads breaching their SLA — action these promptly.
      </Text>
      {overdue?.count > 0 ? (
        <Table
          dataSource={overdue?.leads || []}
          columns={overdueCols}
          rowKey="lead_id"
          size="small"
          pagination={{ pageSize: 10 }}
          style={{ marginBottom: 24 }}
          rowClassName={(r) => (r.worst_hours >= 72 ? 'ant-table-row-danger' : '')}
        />
      ) : (
        <Empty description="No overdue or stale leads 🎉" style={{ margin: 20 }} />
      )}

      <Title level={5} style={{ margin: '16px 0 4px' }}>Campaign Performance</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        Leads, conversion and roadside engagement (cards / people stopped) per campaign.
      </Text>
      <Table
        dataSource={campaigns?.campaigns || []}
        columns={campaignCols}
        rowKey="id"
        size="small"
        pagination={false}
        style={{ marginBottom: 24 }}
      />

      <Title level={5} style={{ margin: '16px 0 4px' }}>Win / Loss Analysis</Title>
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{wlSum?.won || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Won</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#cf1322' }}>{wlSum?.lost || 0}</div><Text type="secondary" style={{ fontSize: 11 }}>Lost</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: wlSum?.win_rate >= 50 ? '#52c41a' : '#cf1322' }}>{wlSum?.win_rate || 0}%</div><Text type="secondary" style={{ fontSize: 11 }}>Win Rate</Text></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{fmt(wlSum?.won_value)}</div><Text type="secondary" style={{ fontSize: 11 }}>Won Value</Text></Card>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>By Source</Text>
          <Table dataSource={winLoss?.by_source || []} columns={wlSourceCols} rowKey="key" size="small" pagination={false} style={{ marginBottom: 24 }} />
        </Col>
        <Col xs={24} md={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>By Agent</Text>
          <Table dataSource={winLoss?.by_agent || []} columns={wlAgentCols} rowKey="key" size="small" pagination={false} style={{ marginBottom: 24 }} />
        </Col>
      </Row>

      <Title level={5} style={{ margin: '8px 0 12px' }}>Pipeline Funnel</Title>
      <Row gutter={16}>
        {(funnel?.funnel || []).map(f => (
          <Col span={4} key={f.stage}>
            <Card size="small" style={{ textAlign: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{f.count}</div>
              <Tag color={f.stage === 'CONVERTED' ? 'green' : f.stage === 'NEW' ? 'blue' : 'default'}>{f.stage}</Tag>
              {f.dropoff_pct != null && f.dropoff_pct > 0 && (
                <div style={{ fontSize: 11, color: '#ff4d4f' }}>▼ {f.dropoff_pct}% drop</div>
              )}
            </Card>
          </Col>
        ))}
      </Row>
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
  const [sources, setSources] = useState([])
  const [helpOpen, setHelpOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Auto-refresh: bump refreshKey on an interval so new/changed content appears
  // without a manual page refresh. Pauses while any modal/drawer is open.
  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(() => setRefreshKey(k => k + 1), 30000) // every 30s
    return () => clearInterval(id)
  }, [autoRefresh])

  // Responsive: treat anything below md (768px) as mobile — catches iPhones/Android.
  const screens = Grid.useBreakpoint()
  const isMobile = !screens.md

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

  useEffect(() => {
    if (!user) return
    api.listSources().then(setSources).catch(() => { /* non-fatal */ })
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
  const isAgent = role === 'AGENT'
  const canWrite = isAdmin || isAgent  // VIEWER is read-only
  const isMultiClientAdmin = role === 'SYSTEM_ADMIN'

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      {/* Header — compact drawer menu on mobile, full bar on desktop */}
      <Layout.Header style={{
        background: '#001529', display: 'flex', alignItems: 'center', gap: 12,
        padding: isMobile ? '0 12px' : '0 24px', height: isMobile ? 52 : 64, lineHeight: isMobile ? '52px' : '64px',
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        <Title level={4} style={{ color: '#fff', margin: 0, fontSize: isMobile ? 16 : 20, whiteSpace: 'nowrap' }}>
          RankBuilder CRM
        </Title>

        {!isMobile && clients.length > 0 && isMultiClientAdmin && (
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

        {isMobile ? (
          <Button icon={<MenuOutlined />} onClick={() => setMenuOpen(true)}
            style={{ color: '#fff', borderColor: '#fff5' }} ghost size="small">
            Menu
          </Button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, whiteSpace: 'nowrap' }}>
              <span style={{ color: '#fff', fontSize: 13, lineHeight: 1.2 }}>{user.full_name}</span>
              <span style={{ color: '#fff5', fontSize: 11 }}>{user.role}</span>
            </div>
            <Button icon={<QuestionCircleOutlined />} onClick={() => setHelpOpen(true)}
              style={{ color: '#fff', borderColor: '#fff5' }} ghost size="small">
              Help
            </Button>
            <Button
              icon={autoRefresh ? <CheckCircleOutlined /> : <FieldTimeOutlined />}
              onClick={() => setAutoRefresh(v => !v)}
              style={{ color: '#fff', borderColor: '#fff5' }} ghost size="small"
              title="Auto-refresh: new/changed content appears without manual refresh"
            >
              {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
            </Button>
            <Button icon={<LogoutOutlined />} onClick={handleLogout}
              style={{ color: '#fff', borderColor: '#fff5' }} ghost size="small">
              Logout
            </Button>
          </div>
        )}
      </Layout.Header>

      {/* Mobile menu drawer */}
      {isMobile && (
        <Drawer title="Menu" placement="right" open={menuOpen} onClose={() => setMenuOpen(false)} width={260}>
          <div style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid #f0f0f0' }}>
            <div style={{ fontWeight: 600 }}>{user.full_name}</div>
            <div style={{ color: '#888', fontSize: 13 }}>{user.role}</div>
          </div>

          {clients.length > 0 && isMultiClientAdmin && (
            <div style={{ marginBottom: 16 }}>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>CLIENT</Text>
              <Select
                value={selectedClientId}
                onChange={id => { setSelectedClientId(id); setRefreshKey(k => k + 1) }}
                style={{ width: '100%' }}
                placeholder="Select client"
              >
                {clients.map(c => (
                  <Select.Option key={c.id} value={c.id}>{c.company_name}</Select.Option>
                ))}
              </Select>
            </div>
          )}

          <Menu
            mode="inline"
            selectedKeys={[tab]}
            onClick={({ key }) => { setTab(key); setMenuOpen(false) }}
            style={{ borderInlineEnd: 'none' }}
            items={[
              { key: 'dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
              { key: 'leads', icon: <DatabaseOutlined />, label: 'Leads' },
              ...(isAdmin ? [{ key: 'campaigns', icon: <FlagOutlined />, label: 'Campaigns' }] : []),
              ...(isAdmin ? [{ key: 'users', icon: <UserOutlined />, label: 'Users' }] : []),
              ...(isMultiClientAdmin ? [{ key: 'clients', icon: <GlobalOutlined />, label: 'Clients' }] : []),
              ...(isMultiClientAdmin ? [{ key: 'sources', icon: <TagsOutlined />, label: 'Sources' }] : []),
              ...(isMultiClientAdmin ? [{ key: 'scoring', icon: <ThunderboltOutlined />, label: 'Scoring' }] : []),
              ...(isAdmin ? [{ key: 'reports', icon: <BarChartOutlined />, label: 'Reports' }] : []),
            ]}
          />

          <div style={{ marginTop: 24 }}>
            <Button icon={<QuestionCircleOutlined />} onClick={() => { setHelpOpen(true); setMenuOpen(false) }} block>
              Help
            </Button>
            <Button icon={<LogoutOutlined />} onClick={handleLogout} danger block style={{ marginTop: 8 }}>
              Logout
            </Button>
          </div>
        </Drawer>
      )}

      {/* Content */}
      <Layout.Content style={{ padding: isMobile ? '12px' : '16px 24px' }}>
        {selectedClientId ? (
          <Tabs activeKey={tab} onChange={setTab} tabBarStyle={isMobile ? { marginBottom: 8 } : undefined}>
            <TabPane tab={<span><DashboardOutlined /> Dashboard</span>} key="dashboard">
              <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                <Dashboard clientId={selectedClientId} key={`dash-${selectedClientId}-${refreshKey}`} />
              </div>
            </TabPane>

            <TabPane tab={<span><DatabaseOutlined /> Leads</span>} key="leads">
              <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                <LeadsTab
                  clientId={selectedClientId}
                  refreshKey={refreshKey}
                  campaignFilter={campaignFilter}
                  campaignName={campaignName}
                  canWrite={canWrite}
                  currentUserEmail={user.email}
                  sources={sources}
                  onSourcesChange={setSources}
                  onClearCampaign={() => {
                    setCampaignFilter(null)
                    setCampaignName(null)
                  }}
                />
              </div>
            </TabPane>

            {isAdmin && (
              <TabPane tab={<span><FlagOutlined /> Campaigns</span>} key="campaigns">
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
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
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                  <UsersTab user={user} clients={clients} />
                </div>
              </TabPane>
            )}

            {isMultiClientAdmin && (
              <TabPane tab={<span><GlobalOutlined /> Clients</span>} key="clients">
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                  <ClientsTab onClientAdded={() => setRefreshKey(k => k + 1)} />
                </div>
              </TabPane>
            )}

            {isMultiClientAdmin && (
              <TabPane tab={<span><TagsOutlined /> Sources</span>} key="sources">
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                  <SourcesTab sources={sources} onSourcesChange={setSources} />
                </div>
              </TabPane>
            )}

            {isMultiClientAdmin && (
              <TabPane tab={<span><ThunderboltOutlined /> Scoring</span>} key="scoring">
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                  <ScoringRulesTab />
                </div>
              </TabPane>
            )}

            {isAdmin && (
              <TabPane tab={<span><BarChartOutlined /> Reports</span>} key="reports">
                <div style={{ background: '#fff', borderRadius: 8, padding: isMobile ? 12 : 16 }}>
                  <ReportsTab clientId={selectedClientId} />
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

      {/* Help modal */}
      <Modal
        title="📚 RankBuilder CRM Help"
        open={helpOpen}
        onCancel={() => setHelpOpen(false)}
        footer={<Button onClick={() => setHelpOpen(false)}>Close</Button>}
        width={520}
      >
        <p style={{ color: '#555' }}>Choose a guide to get started:</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card size="small" hoverable onClick={() => window.open('/help/agent', '_blank')}>
            <Text strong>👤 Agent Guide</Text>
            <div style={{ color: '#888', fontSize: 12 }}>For sales reps — working leads, quotes, AI drafts, scoring, commissions</div>
          </Card>
          <Card size="small" hoverable onClick={() => window.open('/help/admin', '_blank')}>
            <Text strong>🛠️ Admin Guide</Text>
            <div style={{ color: '#888', fontSize: 12 }}>For managers — roles, users, sources, scoring rules, SLA, reports</div>
          </Card>
        </div>
      </Modal>
    </Layout>
  )
}

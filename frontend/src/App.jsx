import { useCallback, useEffect, useState } from 'react'
import { api, clearSession, getSession, saveSession } from './api'
import './App.css'

const emptyRefund = {
  transaction_id: '', amount: '', currency: 'INR',
  webhook_url: 'https://merchant.example/webhooks',
  recipient: 'customer@example.com',
}
const statuses = ['pending', 'running', 'completed', 'failed', 'dead']
const short = (id) => id ? id.slice(0, 8) + '…' : '—'
const when = (value) => value ? new Date(value).toLocaleString() : '—'
const pretty = (value) => value?.replaceAll('_', ' ') || '—'
function Status({ value }) { return <span className={'status ' + value}>{value === 'failed' ? 'retrying' : value}</span> }
function Empty({ title, detail }) { return <div className="empty"><span>◌</span><h3>{title}</h3><p>{detail}</p></div> }

function JobTable({ jobs, open }) {
  if (!jobs.length) return <Empty title="No jobs here yet" detail="Submit a refund to see your queue come to life." />
  return <div className="table-wrap"><table><thead><tr><th>Job ID</th><th>Type</th><th>Priority</th><th>Status</th><th>Created</th><th></th></tr></thead>
    <tbody>{jobs.map((job) => <tr key={job.id}>
      <td className="mono">{short(job.id)}</td><td className="capitalize">{pretty(job.job_type)}</td>
      <td><span className={'priority ' + job.priority}>{job.priority}</span></td>
      <td><Status value={job.status} /></td><td>{when(job.created_at)}</td>
      <td><button className="link-button" onClick={() => open(job)}>Details →</button></td>
    </tr>)}</tbody></table></div>
}

export default function App() {
  const [session, setSession] = useState(getSession)
  const [user, setUser] = useState(null)
  const [page, setPage] = useState('overview')
  const [mode, setMode] = useState('login')
  const [auth, setAuth] = useState({ username: '', email: '', password: '' })
  const [refund, setRefund] = useState(emptyRefund)
  const [jobs, setJobs] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [rate, setRate] = useState(null)
  const [dead, setDead] = useState([])
  const [filter, setFilter] = useState('all')
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!getSession()) return
    try {
      const [profile, jobData, summary, failure] = await Promise.all([
        api('/auth/me/'), api('/jobs/'), api('/metrics/summary/'), api('/metrics/failure-rate/'),
      ])
      setUser(profile)
      setJobs(Array.isArray(jobData) ? jobData : jobData.results || [])
      setMetrics(summary)
      setRate(failure)
      if (profile.is_staff) {
        const letters = await api('/dlq/')
        setDead(Array.isArray(letters) ? letters : letters.results || [])
      }
      setError('')
    } catch (err) {
      if (err.status === 401) {
        clearSession(); setSession(null); setUser(null)
        setError('Your session expired. Sign in again.')
      } else setError(err.message)
    }
  }, [])

  useEffect(() => {
    if (!session) return undefined
    queueMicrotask(refresh)
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [session, refresh])

  async function submitAuth(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const path = mode === 'login' ? '/auth/login/' : '/auth/register/'
      const data = mode === 'login' ? { username: auth.username, password: auth.password } : auth
      const result = await api(path, { method: 'POST', body: data }, false)
      const tokens = result.tokens || result
      saveSession(tokens); setSession(tokens); setAuth({ username: '', email: '', password: '' })
      setPage('overview')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function logout() {
    try {
      if (getSession()?.refresh) await api('/auth/logout/', {
        method: 'POST', body: { refresh: getSession().refresh },
      })
    } catch { /* Clear local session even when API is unavailable. */ }
    clearSession(); setSession(null); setUser(null); setJobs([]); setMetrics(null); setDetail(null)
  }

  async function submitRefund(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const result = await api('/jobs/submit/', {
        method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: {
          job_type: 'refund_processing',
          payload: {
            transaction_id: refund.transaction_id.trim(), amount: refund.amount,
            currency: refund.currency, webhook_url: refund.webhook_url.trim(),
            notification: { channel: 'email', recipient: refund.recipient.trim() },
          },
        },
      })
      setNotice('Refund job ' + short(result.id) + ' queued. Follow its progress below.')
      setRefund(emptyRefund); setPage('jobs'); await refresh()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function openJob(job) {
    setDetail(job)
    try { setDetail(await api('/jobs/' + job.id + '/')) }
    catch (err) { setError(err.message) }
  }

  async function requeue(item) {
    setBusy(true); setError('')
    try {
      await api('/dlq/' + item.id + '/requeue/', { method: 'POST' })
      setNotice('Job ' + short(item.original_job_id) + ' requeued.')
      await refresh()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  if (!session) return <div className="auth-page">
    <div className="auth-hero">
      <div className="brand"><span className="brand-mark">FQ</span> FinQueue</div>
      <div className="auth-hero-main"><span className="eyebrow">ASYNC REFUND OPERATIONS</span>
        <h1>Every refund.<br /><em>Under control.</em></h1>
        <p>Submit refund jobs, follow their progress, and see how queues, retries, and recovery work together.</p>
        <div className="hero-flow"><span>Submit</span> → <span>Process</span> → <span>Track</span></div>
      </div><p className="hero-foot">Django · React · MySQL · Redis</p>
    </div>
    <div className="auth-panel"><div className="auth-card">
      <span className="eyebrow">WELCOME TO FINQUEUE</span>
      <h2>{mode === 'login' ? 'Sign in to your workspace' : 'Create your workspace'}</h2>
      <p className="muted">{mode === 'login' ? 'Your queue is ready when you are.' : 'Start tracking your refund jobs in minutes.'}</p>
      {error && <div className="alert error" role="alert">{error}</div>}
      <form onSubmit={submitAuth} className="stack">
        <label>Username<input value={auth.username} onChange={(e) => setAuth({ ...auth, username: e.target.value })} autoComplete="username" required /></label>
        {mode === 'register' && <label>Email<input type="email" value={auth.email} onChange={(e) => setAuth({ ...auth, email: e.target.value })} autoComplete="email" required /></label>}
        <label>Password<input type="password" value={auth.password} onChange={(e) => setAuth({ ...auth, password: e.target.value })} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 8 : undefined} required /></label>
        <button className="button primary full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in →' : 'Create account →'}</button>
      </form>
      <p className="auth-switch">{mode === 'login' ? 'New to FinQueue?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>
    </div></div>
  </div>

  const visible = jobs.filter((job) => filter === 'all' || job.status === filter)
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">FQ</span> FinQueue</div>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button className={page === 'overview' ? 'active' : ''} onClick={() => setPage('overview')}>◫ <span>Overview</span></button>
        <button className={page === 'jobs' ? 'active' : ''} onClick={() => setPage('jobs')}>▤ <span>Jobs</span><small>{metrics?.total_jobs ?? 0}</small></button>
        <button className={page === 'new' ? 'active' : ''} onClick={() => setPage('new')}>＋ <span>New refund</span></button>
        {user?.is_staff && <button className={page === 'dead' ? 'active' : ''} onClick={() => setPage('dead')}>◇ <span>Dead letters</span><small>{dead.length}</small></button>}
      </nav><div className="sidebar-foot"><i /> Local workspace</div>
    </aside>
    <main className="main">
      <header className="topbar"><div>Workspace <span>/</span> <b>{page === 'new' ? 'New refund' : page === 'dead' ? 'Dead letters' : page[0].toUpperCase() + page.slice(1)}</b></div>
        <div className="top-actions"><button className="icon-button" onClick={refresh} aria-label="Refresh">↻</button><span className="avatar">{user?.username?.[0]?.toUpperCase() || 'U'}</span><b>{user?.username}</b><button className="signout" onClick={logout}>Sign out</button></div>
      </header>
      <div className="content">
        {error && <div className="alert error" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
        {notice && <div className="alert success" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
        {page === 'overview' && <>
          <div className="page-head"><div><span className="eyebrow">OPERATIONS DASHBOARD</span><h1>Welcome back{user ? ', ' + user.username : ''}.</h1><p>Here is what is happening across your refund queue.</p></div><button className="button primary" onClick={() => setPage('new')}>＋ New refund</button></div>
          <div className="stats">
            {[
              ['Total jobs', metrics?.total_jobs, '▤'],
              ['In progress', (metrics?.pending || 0) + (metrics?.running || 0), '◷'],
              ['Completed', metrics?.completed, '✓'],
              ['Needs attention', (metrics?.failed || 0) + (metrics?.dead || 0), '!'],
            ].map(([label, value, icon]) => <div className="stat" key={label}><div>{label}<span>{icon}</span></div><strong>{value ?? '—'}</strong><i /></div>)}
          </div>
          <div className="overview-grid"><section className="card"><div className="card-head"><div><h2>Recent jobs</h2><p>Latest activity in your queue</p></div><button className="link-button" onClick={() => setPage('jobs')}>View all →</button></div><JobTable jobs={jobs.slice(0, 5)} open={openJob} /></section>
          <section className="card health"><div className="card-head"><div><h2>Queue health</h2><p>Current operational snapshot</p></div></div><div className="health-circle"><strong>{rate ? Math.max(0, 100 - rate.failure_rate_percent) + '%' : '—'}</strong><span>healthy jobs</span></div><div className="health-rows"><div>Pending <b>{metrics?.pending ?? 0}</b></div><div>Running <b>{metrics?.running ?? 0}</b></div><div>Failed / dead <b>{(metrics?.failed || 0) + (metrics?.dead || 0)}</b></div></div></section></div>
        </>}
        {page === 'jobs' && <><div className="page-head"><div><span className="eyebrow">QUEUE ACTIVITY</span><h1>Jobs</h1><p>Track every refund and its follow-up work.</p></div><button className="button primary" onClick={() => setPage('new')}>＋ New refund</button></div><section className="card"><div className="card-head"><div><h2>All jobs <span className="count">{visible.length}</span></h2><p>Updates every 5 seconds</p></div><select aria-label="Filter by status" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{value}</option>)}</select></div><JobTable jobs={visible} open={openJob} /></section></>}
        {page === 'new' && <><div className="page-head"><div><span className="eyebrow">CREATE A JOB</span><h1>New refund</h1><p>Submit a refund and watch it move through the queue.</p></div></div><div className="form-layout"><section className="card form-card"><h2>Refund details</h2><p className="muted">FinQueue assigns the priority and queues follow-up jobs automatically.</p><form className="form-grid" onSubmit={submitRefund}>
          <label>Transaction ID<input value={refund.transaction_id} onChange={(e) => setRefund({ ...refund, transaction_id: e.target.value })} placeholder="txn-1001" required /></label>
          <label>Amount<input type="number" min="0.01" step="0.01" value={refund.amount} onChange={(e) => setRefund({ ...refund, amount: e.target.value })} placeholder="1000.00" required /></label>
          <label>Currency<input value={refund.currency} onChange={(e) => setRefund({ ...refund, currency: e.target.value.toUpperCase() })} maxLength={3} required /></label>
          <label>Notification email<input type="email" value={refund.recipient} onChange={(e) => setRefund({ ...refund, recipient: e.target.value })} required /></label>
          <label className="span-two">Merchant webhook URL<input type="url" value={refund.webhook_url} onChange={(e) => setRefund({ ...refund, webhook_url: e.target.value })} required /></label>
          <div className="span-two"><button className="button primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit refund →'}</button></div>
        </form></section><aside className="card explainer"><span className="eyebrow">WHAT HAPPENS NEXT</span><h2>One request.<br />A reliable workflow.</h2><ol><li><b>Queue</b><span>Your refund enters the high-priority queue.</span></li><li><b>Process</b><span>A worker handles it and retries transient failures.</span></li><li><b>Follow up</b><span>Webhooks and notifications run as separate jobs.</span></li></ol><p>This is a simulation. Use sample transaction and customer data.</p></aside></div></>}
        {page === 'dead' && user?.is_staff && <><div className="page-head"><div><span className="eyebrow">ADMIN OPERATIONS</span><h1>Dead-letter queue</h1><p>Review jobs that exhausted retries and requeue them.</p></div></div><section className="card"><div className="card-head"><h2>Dead letters <span className="count">{dead.length}</span></h2></div>{dead.length ? <div className="table-wrap"><table><thead><tr><th>Job</th><th>Type</th><th>Reason</th><th>Attempts</th><th>Died</th><th></th></tr></thead><tbody>{dead.map((item) => <tr key={item.id}><td className="mono">{short(item.original_job_id)}</td><td className="capitalize">{pretty(item.job_type)}</td><td>{item.failure_reason || '—'}</td><td>{item.retry_attempts}</td><td>{when(item.died_at)}</td><td><button className="link-button" disabled={busy} onClick={() => requeue(item)}>Requeue →</button></td></tr>)}</tbody></table></div> : <Empty title="No dead letters" detail="Jobs that exhaust all retries will appear here." />}</section></>}
      </div>
    </main>
    {detail && <div className="drawer-backdrop" onClick={() => setDetail(null)}><aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="Job details"><div className="drawer-head"><div><span className="eyebrow">JOB DETAILS</span><h2>{short(detail.id)}</h2></div><button className="icon-button" onClick={() => setDetail(null)}>×</button></div><div className="drawer-status">Status <Status value={detail.status} /></div><dl>{[['Type', pretty(detail.job_type)], ['Priority', detail.priority], ['Retries', detail.retry_count], ['Created', when(detail.created_at)], ['Updated', when(detail.updated_at)], ['Source job', detail.source_job ? short(detail.source_job) : '—']].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>{detail.failure_reason && <div className="detail-block"><h3>Failure reason</h3><p>{detail.failure_reason}</p></div>}<div className="detail-block"><h3>Payload</h3><pre>{JSON.stringify(detail.payload, null, 2)}</pre></div>{detail.result && <div className="detail-block"><h3>Result</h3><pre>{JSON.stringify(detail.result, null, 2)}</pre></div>}</aside></div>}
  </div>
}


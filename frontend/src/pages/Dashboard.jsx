import { useState, useEffect } from 'react'
import { getProfile, updateProfile } from '../api'

export default function Dashboard() {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({
    naukri_username: '',
    naukri_password: '',
    resume_drive_link: '',
    headline_1: '',
    headline_2: '',
    summary_1: '',
    summary_2: '',
    refresh_interval: 3600,
    is_active: true,
  })
  const [intervalVal, setIntervalVal] = useState(1)
  const [intervalUnit, setIntervalUnit] = useState(3600)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    loadProfile()
  }, [])

  async function loadProfile() {
    try {
      const data = await getProfile()
      if (data) {
        setProfile(data)
        setForm(prev => ({
          ...prev,
          naukri_username: data.naukri_username || '',
          resume_drive_link: data.resume_drive_link || '',
          headline_1: data.headline_1 || '',
          headline_2: data.headline_2 || '',
          summary_1: data.summary_1 || '',
          summary_2: data.summary_2 || '',
          refresh_interval: data.refresh_interval || 3600,
          is_active: data.is_active ?? true,
          naukri_password: '', // Never pre-fill password
        }))

        // Setup interval UI state
        const ri = data.refresh_interval || 3600
        if (ri % 3600 === 0) {
          setIntervalVal(ri / 3600)
          setIntervalUnit(3600)
        } else if (ri % 60 === 0) {
          setIntervalVal(ri / 60)
          setIntervalUnit(60)
        } else {
          setIntervalVal(ri)
          setIntervalUnit(1)
        }
      }
    } catch (err) {
      setError('Failed to load profile')
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setMessage('')
    setError('')

    try {
      const payload = { ...form }
      // Don't send empty password (means "no change")
      if (!payload.naukri_password) delete payload.naukri_password
      const updated = await updateProfile(payload)
      setProfile(updated)
      setMessage('Settings saved successfully!')
      setTimeout(() => setMessage(''), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  function handleChange(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleIntervalUpdate(val, unit) {
    setIntervalVal(val)
    setIntervalUnit(unit)
    handleChange('refresh_interval', Math.max(1, parseInt(val || 1)) * parseInt(unit))
  }

  function timeAgo(isoDate) {
    if (!isoDate) return 'Never'
    const diff = Date.now() - new Date(isoDate).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins} min ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs} hr ago`
    return `${Math.floor(hrs / 24)} days ago`
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <p>Configure your Naukri profile automation settings</p>
      </div>

      {/* Status Card */}
      {profile && (
        <div className="status-card">
          <div className="status-row">
            <div className="status-item">
              <span className="status-label">Status</span>
              <span className={`status-badge ${profile.is_active ? 'active' : 'inactive'}`}>
                {profile.is_active ? '● Active' : '○ Inactive'}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Last Refresh</span>
              <span className="status-value">{timeAgo(profile.last_refreshed)}</span>
            </div>
            <div className="status-item">
              <span className="status-label">Last Status</span>
              <span className={`status-value ${profile.last_status === 'success' ? 'text-success' : 'text-error'}`}>
                {profile.last_status ? (profile.last_status === 'success' ? '✓ Success' : '✗ Failed') : '—'}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Total Refreshes</span>
              <span className="status-value">{profile.total_refreshes || 0}</span>
            </div>
          </div>
          {profile.last_error && (
            <div className="status-error">Last error: {profile.last_error}</div>
          )}
        </div>
      )}

      {/* Messages */}
      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {/* Settings Form */}
      <form onSubmit={handleSave} className="settings-form">
        <div className="form-section">
          <h2>Naukri Account</h2>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="naukri-email">Naukri Email</label>
              <input
                id="naukri-email"
                type="email"
                value={form.naukri_username}
                onChange={e => handleChange('naukri_username', e.target.value)}
                placeholder="your-naukri-email@example.com"
              />
            </div>
            <div className="form-group">
              <label htmlFor="naukri-pass">Naukri Password</label>
              <input
                id="naukri-pass"
                type="password"
                value={form.naukri_password}
                onChange={e => handleChange('naukri_password', e.target.value)}
                placeholder={profile?.naukri_username ? '••••••• (leave empty to keep current)' : 'Enter password'}
              />
            </div>
          </div>
        </div>

        <div className="form-section">
          <h2>Resume</h2>
          <div className="form-group">
            <label htmlFor="drive-link">Google Drive Link</label>
            <input
              id="drive-link"
              type="url"
              value={form.resume_drive_link}
              onChange={e => handleChange('resume_drive_link', e.target.value)}
              placeholder="https://drive.google.com/file/d/YOUR_FILE_ID/view"
            />
            <span className="form-hint">Make sure the file is set to "Anyone with the link can view"</span>
          </div>
        </div>

        <div className="form-section">
          <h2>Headlines</h2>
          <p className="form-section-desc">Two headlines that alternate every refresh cycle</p>
          <div className="form-group">
            <label htmlFor="h1">Headline A</label>
            <textarea
              id="h1"
              value={form.headline_1}
              onChange={e => handleChange('headline_1', e.target.value)}
              placeholder="Fullstack Developer with 6 years of experience in ASP.NET Core, C#, Azure..."
              rows={2}
            />
          </div>
          <div className="form-group">
            <label htmlFor="h2">Headline B</label>
            <textarea
              id="h2"
              value={form.headline_2}
              onChange={e => handleChange('headline_2', e.target.value)}
              placeholder="Senior .NET Developer | 6+ yrs | ASP.NET Core, Azure, React.js..."
              rows={2}
            />
          </div>
        </div>

        <div className="form-section">
          <h2>Summaries</h2>
          <p className="form-section-desc">Two profile summaries that alternate every refresh cycle</p>
          <div className="form-group">
            <label htmlFor="s1">Summary A</label>
            <textarea
              id="s1"
              value={form.summary_1}
              onChange={e => handleChange('summary_1', e.target.value)}
              placeholder="Results-driven developer with expertise in..."
              rows={4}
            />
          </div>
          <div className="form-group">
            <label htmlFor="s2">Summary B</label>
            <textarea
              id="s2"
              value={form.summary_2}
              onChange={e => handleChange('summary_2', e.target.value)}
              placeholder="Experienced engineer specializing in..."
              rows={4}
            />
          </div>
        </div>

        <div className="form-section">
          <h2>Settings</h2>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="interval-val">Refresh Interval</label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  id="interval-val"
                  type="number"
                  min="1"
                  step="1"
                  value={intervalVal}
                  onChange={e => handleIntervalUpdate(e.target.value, intervalUnit)}
                  style={{ width: '80px' }}
                />
                <select
                  value={intervalUnit}
                  onChange={e => handleIntervalUpdate(intervalVal, e.target.value)}
                  style={{ flex: 1 }}
                >
                  <option value={1}>Seconds</option>
                  <option value={60}>Minutes</option>
                  <option value={3600}>Hours</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="active-toggle">Automation</label>
              <label className="toggle">
                <input
                  id="active-toggle"
                  type="checkbox"
                  checked={form.is_active}
                  onChange={e => handleChange('is_active', e.target.checked)}
                />
                <span className="toggle-slider"></span>
                <span className="toggle-label">{form.is_active ? 'Active' : 'Paused'}</span>
              </label>
            </div>
          </div>
        </div>

        <button type="submit" className="btn btn-primary btn-lg btn-full" disabled={saving}>
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </form>
    </div>
  )
}

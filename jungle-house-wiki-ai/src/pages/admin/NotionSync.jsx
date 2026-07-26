import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function NotionSync() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;

  const [form, setForm] = useState({ token: '', source: '' });
  const [currentConfig, setCurrentConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [syncResult, setSyncResult] = useState(null);
  const [jobs, setJobs] = useState([]);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await api.get('/notion-sync/config');
      setCurrentConfig(response.data?.config || null);
    } catch (error) {
      console.error('Fetch Notion sync config error:', error);
      setMessage('Failed to load Notion sync settings.');
    } finally {
      setLoading(false);
    }
  };

  const fetchJobs = async () => {
    try {
      const response = await api.get('/notion-sync/jobs');
      setJobs(Array.isArray(response.data?.jobs) ? response.data.jobs : []);
    } catch (error) {
      console.error('Fetch Notion sync jobs error:', error);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchJobs();
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setTestResult(null);
  };

  const handleTestConnection = async () => {
    try {
      setTesting(true);
      setMessage('');
      setTestResult(null);

      const response = await api.post('/notion-sync/test', {
        user_id: actorId,
        token: form.token.trim(),
        source: form.source.trim(),
      });

      setTestResult({
        success: Boolean(response.data?.success),
        message: response.data?.message || 'Test completed.',
      });
    } catch (error) {
      console.error('Test Notion connection error:', error);
      setTestResult({
        success: false,
        message:
          error.response?.data?.message ||
          'Notion connection failed. Please check your token and sharing permission.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (event) => {
    event.preventDefault();

    if (!form.token.trim() || !form.source.trim()) {
      setMessage('Notion token and page/database URL or ID are both required.');
      return;
    }

    try {
      setSaving(true);
      setMessage('');

      const response = await api.post('/notion-sync/config', {
        updated_by: actorId,
        token: form.token.trim(),
        source: form.source.trim(),
      });

      setMessage(response.data?.message || 'Notion sync settings saved successfully.');
      setCurrentConfig(response.data?.config || null);
      setTestResult(null);
      setForm((prev) => ({ ...prev, token: '' }));
    } catch (error) {
      console.error('Save Notion sync config error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to save Notion sync settings.'
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSyncNow = async () => {
    try {
      setSyncing(true);
      setMessage('');
      setSyncResult(null);

      const response = await api.post('/notion-sync/run', { user_id: actorId });

      setSyncResult(response.data);
      fetchJobs();
    } catch (error) {
      console.error('Run Notion sync error:', error);
      setMessage(
        error.response?.data?.message || 'Some articles failed to import. Please check sync history.'
      );
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Notion Sync"
        subtitle="Copy Notion pages into your own Knowledge Base database so they work like normal articles."
      />

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      <section className="card-like top-gap-sm">
        <h3>Connected Notion Source</h3>

        {loading ? (
          <p className="muted top-gap-sm">Loading...</p>
        ) : currentConfig ? (
          <div className="cards-grid top-gap-sm">
            <p className="muted">
              Source: <strong>{currentConfig.sourceName || currentConfig.sourceId}</strong>
            </p>
            <p className="muted">
              Token: <strong>{currentConfig.tokenHint}</strong>
            </p>
            <p className="muted">
              Last Updated: <strong>{currentConfig.updatedAt || '-'}</strong>
            </p>
          </div>
        ) : (
          <p className="muted top-gap-sm">
            No Notion source connected yet. Connect one below before syncing.
          </p>
        )}
      </section>

      <section className="card-like top-gap">
        <h3>Connect Notion</h3>
        <p className="muted">
          Paste your Notion Integration Token once — it's encrypted and stored
          securely, and is never shown again after saving. Make sure the page
          or database is shared with your integration first.
        </p>

        <form className="form-grid top-gap" onSubmit={handleSave}>
          <label className="full-width">
            Notion Integration Token
            <input
              type="password"
              name="token"
              value={form.token}
              onChange={handleChange}
              placeholder={
                currentConfig
                  ? 'Enter a new token to replace the saved one'
                  : 'Paste Notion integration token here'
              }
              autoComplete="off"
            />
          </label>

          <label className="full-width">
            Notion Page / Database URL or ID
            <input
              type="text"
              name="source"
              value={form.source}
              onChange={handleChange}
              placeholder="Paste a Notion page/database URL or ID"
            />
          </label>

          {testResult && (
            <p
              className={`full-width ${testResult.success ? 'success-text' : 'error-text'}`}
            >
              {testResult.message}
            </p>
          )}

          <div className="full-width button-group wrap-gap">
            <button
              type="button"
              className="secondary-btn"
              onClick={handleTestConnection}
              disabled={testing}
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>

            <button className="primary-btn" type="submit" disabled={saving}>
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </form>
      </section>

      <section className="card-like top-gap">
        <div className="row-between wrap-gap">
          <div>
            <h3>Sync Now</h3>
            <p className="muted">
              Imports new/changed pages from the connected Notion source into
              your Knowledge Base. Already-imported, unchanged pages are
              skipped — safe to click multiple times.
            </p>
          </div>

          <button
            className="primary-btn"
            type="button"
            disabled={syncing || !currentConfig}
            onClick={handleSyncNow}
          >
            {syncing ? 'Syncing Notion articles into Knowledge Base...' : 'Sync Now'}
          </button>
        </div>

        {syncResult && (
          <div className="cards-grid top-gap-sm">
            <p className="muted">Imported: <strong>{syncResult.imported}</strong></p>
            <p className="muted">Updated: <strong>{syncResult.updated}</strong></p>
            <p className="muted">Skipped: <strong>{syncResult.skipped}</strong></p>
            <p className="muted">Failed: <strong>{syncResult.failed}</strong></p>
          </div>
        )}
      </section>

      <section className="card-like top-gap">
        <h3>Sync History</h3>

        {jobs.length === 0 ? (
          <p className="muted top-gap-sm">No sync has been run yet.</p>
        ) : (
          <div className="table-card top-gap-sm">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Imported</th>
                  <th>Updated</th>
                  <th>Skipped</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.completed_at || job.started_at || '-'}</td>
                    <td>
                      <span className="role-pill">{job.status}</span>
                    </td>
                    <td>{job.imported_count}</td>
                    <td>{job.updated_count}</td>
                    <td>{job.skipped_count}</td>
                    <td>{job.failed_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

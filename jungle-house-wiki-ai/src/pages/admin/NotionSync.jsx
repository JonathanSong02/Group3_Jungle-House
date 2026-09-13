import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function NotionSync() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [checking, setChecking] = useState(false);
  // Lazy initializer so the OAuth callback's ?connected=1 / ?error=... banner
  // is derived from the URL on first render, not set synchronously inside a
  // useEffect body (which would trigger a redundant extra render).
  const [message, setMessage] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');

    if (connected) return 'Notion connected successfully.';
    if (error) return `Notion connection failed: ${error.replace(/_/g, ' ')}`;
    return '';
  });
  const [checkResult, setCheckResult] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [pending, setPending] = useState([]);
  const [expandedPendingId, setExpandedPendingId] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await api.get('/notion-sync/config');
      setConfig(response.data?.config || null);
    } catch (error) {
      console.error('Fetch Notion sync config error:', error);
      setMessage('Failed to load Notion connection status.');
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

  const fetchPending = async () => {
    try {
      const response = await api.get('/notion-sync/pending-updates');
      setPending(Array.isArray(response.data?.pending) ? response.data.pending : []);
    } catch (error) {
      console.error('Fetch Notion pending updates error:', error);
    }
  };

  const handleCheckForUpdates = async ({ silent } = {}) => {
    try {
      setChecking(true);
      if (!silent) setMessage('');
      setCheckResult(null);

      const response = await api.post('/notion-sync/check', { user_id: actorId });

      setCheckResult(response.data);
      fetchJobs();
      fetchPending();
    } catch (error) {
      console.error('Check Notion for updates error:', error);
      if (!silent) {
        setMessage(
          error.response?.data?.message || 'Failed to check Notion for updates.'
        );
      }
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    // The OAuth callback redirects back here with ?connected=1 or ?error=...
    // -- the banner text itself is derived once in the message state's lazy
    // initializer above; this effect only cleans the URL and kicks off data
    // fetching (the actual "synchronize with an external system" side effects).
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');

    if (connected || error) {
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, '', cleanUrl);
    }

    fetchConfig();
    fetchJobs();
    fetchPending();

    if (connected) {
      // A fresh connection almost certainly has nothing imported yet --
      // check right away instead of waiting for a manual click.
      handleCheckForUpdates({ silent: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // PLACEHOLDER (temporary): the real OAuth flow is fully built on the
  // backend (POST /notion-sync/oauth/start builds a real authorize URL with
  // state/client_id/redirect_uri), but NOTION_OAUTH_CLIENT_ID/SECRET aren't
  // configured on Railway yet, so that call would currently fail. Until
  // that's set up, this just sends the browser straight to Notion's login
  // page as a UI stand-in -- it does NOT authorize anything or import any
  // content. Swap the button below back to calling _handleConnectReal once
  // the Notion integration + Railway env vars are ready.
  const handleConnectPlaceholder = () => {
    window.location.href = 'https://app.notion.com/login';
  };

  const _handleConnectReal = async () => {
    try {
      setConnecting(true);
      setMessage('');

      const response = await api.post('/notion-sync/oauth/start', { user_id: actorId });
      const authorizeUrl = response.data?.authorizeUrl;

      if (!authorizeUrl) {
        throw new Error('No authorization URL returned.');
      }

      window.location.href = authorizeUrl;
    } catch (error) {
      console.error('Start Notion OAuth error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to start connecting to Notion.'
      );
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      setDisconnecting(true);
      setMessage('');

      const response = await api.post('/notion-sync/disconnect', { user_id: actorId });

      setMessage(response.data?.message || 'Notion disconnected.');
      setConfig(null);
      setCheckResult(null);
    } catch (error) {
      console.error('Disconnect Notion error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to disconnect Notion.'
      );
    } finally {
      setDisconnecting(false);
    }
  };

  const handleResolvePending = async (pendingId, action) => {
    try {
      setResolvingId(pendingId);
      setMessage('');

      const response = await api.post(
        `/notion-sync/pending-updates/${pendingId}/${action}`,
        { user_id: actorId }
      );

      setMessage(response.data?.message || 'Done.');
      setPending((prev) => prev.filter((item) => item.id !== pendingId));

      if (expandedPendingId === pendingId) {
        setExpandedPendingId(null);
      }
    } catch (error) {
      console.error(`Resolve Notion pending update (${action}) error:`, error);
      setMessage(
        error.response?.data?.message || 'Failed to resolve this update. It may have already been handled.'
      );
      fetchPending();
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Notion Sync"
        subtitle="Connect Notion once, then copy its content into your own Knowledge Base database so it works like normal articles."
      />

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      <section className="card-like top-gap-sm">
        <h3>Connected Notion Workspace</h3>

        {loading ? (
          <p className="muted top-gap-sm">Loading...</p>
        ) : config?.connected ? (
          <div className="cards-grid top-gap-sm">
            <p className="muted">
              Workspace: <strong>{config.workspaceName || 'Notion workspace'}</strong>
            </p>
            <p className="muted">
              Connected: <strong>{config.updatedAt || '-'}</strong>
            </p>
            <div className="button-group wrap-gap">
              <button
                type="button"
                className="secondary-btn"
                onClick={handleDisconnect}
                disabled={disconnecting}
              >
                {disconnecting ? 'Disconnecting...' : 'Disconnect'}
              </button>
            </div>
          </div>
        ) : (
          <div className="top-gap-sm">
            <p className="muted">
              No Notion workspace connected yet. Click below to sign into Notion
              and choose which pages/databases to share — nothing is changed on
              the Notion side, only copied into this Knowledge Base.
            </p>
            <div className="button-group wrap-gap top-gap-sm">
              <button
                type="button"
                className="primary-btn"
                onClick={handleConnectPlaceholder}
                disabled={connecting}
              >
                {connecting ? 'Redirecting to Notion...' : 'Connect Notion'}
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="card-like top-gap">
        <div className="row-between wrap-gap">
          <div>
            <h3>Check for Updates</h3>
            <p className="muted">
              Imports any new pages shared with your Notion connection, and
              flags edited pages for your review below instead of overwriting
              them automatically. Safe to click multiple times.
            </p>
          </div>

          <button
            className="primary-btn"
            type="button"
            disabled={checking || !config?.connected}
            onClick={() => handleCheckForUpdates()}
          >
            {checking ? 'Checking Notion...' : 'Check for Updates'}
          </button>
        </div>

        {checkResult && (
          <div className="cards-grid top-gap-sm">
            <p className="muted">New: <strong>{checkResult.new}</strong></p>
            <p className="muted">Flagged for review: <strong>{checkResult.flagged}</strong></p>
            <p className="muted">Unchanged: <strong>{checkResult.unchanged}</strong></p>
            <p className="muted">Failed: <strong>{checkResult.failed}</strong></p>
          </div>
        )}
      </section>

      <section className="card-like top-gap">
        <h3>Pending Updates</h3>
        <p className="muted">
          These pages changed in Notion since they were last imported. Choose
          whether to bring in the latest version or keep what's currently
          published.
        </p>

        {pending.length === 0 ? (
          <p className="muted top-gap-sm">No pending updates right now.</p>
        ) : (
          <div className="cards-grid top-gap-sm" style={{ gap: '12px' }}>
            {pending.map((item) => {
              const isExpanded = expandedPendingId === item.id;
              const isResolving = resolvingId === item.id;

              return (
                <div key={item.id} className="card-like">
                  <div className="row-between wrap-gap">
                    <div>
                      <p>
                        <strong>{item.proposed_title || item.previous_title}</strong>
                      </p>
                      <p className="muted">
                        Changed in Notion: {item.notion_last_edited_time || '-'}
                      </p>
                    </div>

                    <div className="button-group wrap-gap">
                      <button
                        type="button"
                        className="secondary-btn"
                        onClick={() => setExpandedPendingId(isExpanded ? null : item.id)}
                      >
                        {isExpanded ? 'Hide preview' : 'Review changes'}
                      </button>
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isResolving}
                        onClick={() => handleResolvePending(item.id, 'dismiss')}
                      >
                        {isResolving ? 'Working...' : 'Keep Current Version'}
                      </button>
                      <button
                        type="button"
                        className="primary-btn"
                        disabled={isResolving}
                        onClick={() => handleResolvePending(item.id, 'apply')}
                      >
                        {isResolving ? 'Working...' : 'Update to Latest'}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="top-gap-sm" style={{ display: 'grid', gap: '16px' }}>
                      <div>
                        <p className="muted"><strong>Current (published)</strong></p>
                        <div
                          className="article-rich-content"
                          dangerouslySetInnerHTML={{ __html: item.previous_content || '' }}
                        />
                      </div>
                      <div>
                        <p className="muted"><strong>Proposed (from Notion)</strong></p>
                        <div
                          className="article-rich-content"
                          dangerouslySetInnerHTML={{ __html: item.proposed_content || '' }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="card-like top-gap">
        <h3>Sync History</h3>

        {jobs.length === 0 ? (
          <p className="muted top-gap-sm">No check has been run yet.</p>
        ) : (
          <div className="table-card top-gap-sm">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Status</th>
                  <th>New</th>
                  <th>Flagged</th>
                  <th>Unchanged</th>
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

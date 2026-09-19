import { useEffect, useRef, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import './styles/NotionSync.css';

// Notion's redirect_uri has to be the backend's own real, stable public
// URL (what's registered in the Notion integration settings) -- NOT the
// "/api" same-origin Vercel proxy path everything else in this app uses --
// so the OAuth popup ends up on the Railway domain directly, same as the
// other places in this app that need the raw backend origin (see
// ArticleDetail.jsx/Chat.jsx's VITE_STATIC_BASE_URL/VITE_BACKEND_PUBLIC_URL
// fallback chain, reused here for the postMessage origin check below).
const NOTION_OAUTH_BACKEND_URL = String(
  import.meta.env.VITE_STATIC_BASE_URL ||
  import.meta.env.VITE_BACKEND_PUBLIC_URL ||
  (typeof window !== 'undefined' &&
    ['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? 'http://127.0.0.1:5000'
    : 'https://group3jungle-house-production.up.railway.app')
).replace(/\/+$/, '');

const NOTION_OAUTH_ORIGIN = new URL(NOTION_OAUTH_BACKEND_URL).origin;

export default function NotionSync() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [checking, setChecking] = useState(false);

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

  const oauthPopupRef = useRef(null);
  const oauthPopupPollRef = useRef(null);

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

      const response = await api.post('/notion-sync/check', {
        user_id: actorId,
      });

      setCheckResult(response.data);
      await Promise.all([fetchJobs(), fetchPending()]);
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

  const stopWatchingOauthPopup = () => {
    if (oauthPopupPollRef.current) {
      clearInterval(oauthPopupPollRef.current);
      oauthPopupPollRef.current = null;
    }
    oauthPopupRef.current = null;
  };

  const finishConnectAttempt = (statusMessage, { connected } = {}) => {
    stopWatchingOauthPopup();
    setConnecting(false);
    if (statusMessage) setMessage(statusMessage);

    fetchConfig();
    if (connected) {
      handleCheckForUpdates({ silent: true });
    } else {
      fetchJobs();
      fetchPending();
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');

    if (connected || error) {
      window.history.replaceState({}, '', window.location.pathname);
    }

    fetchConfig();
    fetchJobs();
    fetchPending();

    if (connected) {
      setMessage('Notion connected successfully.');
      handleCheckForUpdates({ silent: true });
    } else if (error) {
      setMessage(`Notion connection failed: ${error.replace(/_/g, ' ')}`);
    }

    // Primary path: the OAuth callback runs in a popup window (opened by
    // handleConnect below) and posts the result back here via
    // window.postMessage instead of navigating this tab away, so the admin
    // never loses their place on this page. The ?connected=1/?error=...
    // query params handled above are only the fallback for when the popup
    // was blocked and the callback had to redirect this tab directly.
    const handleOauthMessage = (event) => {
      if (event.origin !== NOTION_OAUTH_ORIGIN) return;
      if (!event.data || event.data.source !== 'jungle-house-notion-oauth') return;

      if (event.data.status === 'connected') {
        finishConnectAttempt('Notion connected successfully.', { connected: true });
      } else {
        const detail = event.data.detail || 'connection_failed';
        finishConnectAttempt(`Notion connection failed: ${detail.replace(/_/g, ' ')}`);
      }
    };

    window.addEventListener('message', handleOauthMessage);
    return () => {
      window.removeEventListener('message', handleOauthMessage);
      stopWatchingOauthPopup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setMessage('');

    // Open the popup synchronously (before the await below) so browsers
    // don't treat it as an unrequested popup and block it.
    const popup = window.open(
      '',
      'jungle-house-notion-oauth',
      'width=600,height=720,menubar=no,toolbar=no,status=no'
    );

    try {
      const response = await api.post('/notion-sync/oauth/start', {
        user_id: actorId,
      });

      const authorizeUrl = response.data?.authorizeUrl;

      if (!authorizeUrl) {
        throw new Error('No authorization URL returned.');
      }

      if (popup && !popup.closed) {
        oauthPopupRef.current = popup;
        popup.location.href = authorizeUrl;

        // If the admin closes the popup themselves without finishing
        // login, don't leave the button stuck on "Opening Notion...".
        oauthPopupPollRef.current = setInterval(() => {
          if (oauthPopupRef.current && oauthPopupRef.current.closed) {
            finishConnectAttempt(null);
          }
        }, 500);
      } else {
        // Popup blocked -- fall back to redirecting this tab, same as the
        // callback's own fallback when it finds no opener.
        window.location.href = authorizeUrl;
      }
    } catch (error) {
      if (popup && !popup.closed) popup.close();
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

      const response = await api.post('/notion-sync/disconnect', {
        user_id: actorId,
      });

      setMessage(response.data?.message || 'Notion disconnected.');
      setConfig(null);
      setCheckResult(null);
      setPending([]);
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

      await fetchJobs();
    } catch (error) {
      console.error(`Resolve Notion pending update (${action}) error:`, error);
      setMessage(
        error.response?.data?.message ||
          'Failed to resolve this update. It may have already been handled.'
      );
      fetchPending();
    } finally {
      setResolvingId(null);
    }
  };

  const latestJob = jobs[0] || null;

  return (
    <div className="ns-page">
      <PageHeader
        title="Notion Sync"
        subtitle="Connect Notion and review updates before publishing them."
      />

      {message ? <div className="ns-feedback">{message}</div> : null}

      <section className="ns-summary-grid">
        <div className="ns-summary-card status">
          <span>Connection</span>
          <strong>{config?.connected ? 'Connected' : 'Not connected'}</strong>
        </div>

        <div className="ns-summary-card pending">
          <span>Pending Review</span>
          <strong>{pending.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>Sync Jobs</span>
          <strong>{jobs.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>Last Check</span>
          <strong>{latestJob?.completed_at || latestJob?.started_at || '-'}</strong>
        </div>
      </section>

      <div className="ns-layout">
        <section className="ns-card ns-source-card">
          <div className="ns-section-head">
            <div>
              <span className="ns-kicker">Workspace</span>
              <h2>Notion Connection</h2>
            </div>

            <span className={`ns-status-pill ${config?.connected ? 'connected' : 'idle'}`}>
              <i />
              {config?.connected ? 'Connected' : 'Not connected'}
            </span>
          </div>

          {loading ? (
            <div className="ns-loading">Loading connection...</div>
          ) : config?.connected ? (
            <>
              <div className="ns-source-info">
                <div>
                  <span>Workspace</span>
                  <strong>{config.workspaceName || 'Notion workspace'}</strong>
                </div>

                <div>
                  <span>Connected</span>
                  <strong>{config.updatedAt || '-'}</strong>
                </div>

                <div>
                  <span>Status</span>
                  <strong>Ready</strong>
                </div>
              </div>

              <div className="ns-connection-actions">
                <button
                  type="button"
                  className="ns-btn secondary"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </div>
            </>
          ) : (
            <div className="ns-connect-empty">
              <div className="ns-notion-icon">N</div>
              <div>
                <strong>No workspace connected</strong>
                <p>
                  Sign in to Notion and choose the pages or databases you want
                  to share with this Knowledge Base.
                </p>
              </div>

              <button
                type="button"
                className="ns-btn primary"
                onClick={handleConnect}
                disabled={connecting}
              >
                {connecting ? 'Opening Notion...' : 'Connect Notion'}
              </button>
            </div>
          )}
        </section>

        <section className="ns-card ns-sync-card">
          <div className="ns-sync-hero">
            <div className="ns-notion-icon">N</div>
            <div>
              <span className="ns-kicker">Knowledge Sync</span>
              <h2>Check for Updates</h2>
              <p>Import new pages and flag edited pages for review.</p>
            </div>
          </div>

          <button
            className="ns-sync-btn"
            type="button"
            disabled={checking || !config?.connected}
            onClick={() => handleCheckForUpdates()}
          >
            {checking ? 'Checking Notion...' : 'Check for Updates'}
          </button>

          {checkResult ? (
            <div className="ns-sync-result-grid">
              <div>
                <span>New</span>
                <strong>{checkResult.new ?? 0}</strong>
              </div>
              <div>
                <span>Flagged</span>
                <strong>{checkResult.flagged ?? 0}</strong>
              </div>
              <div>
                <span>Unchanged</span>
                <strong>{checkResult.unchanged ?? 0}</strong>
              </div>
              <div className={Number(checkResult.failed) > 0 ? 'failed' : ''}>
                <span>Failed</span>
                <strong>{checkResult.failed ?? 0}</strong>
              </div>
            </div>
          ) : (
            <div className="ns-sync-note">
              <span>Safe to run again — unchanged pages are skipped.</span>
            </div>
          )}
        </section>
      </div>

      <section className="ns-card ns-pending-section">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">Review Queue</span>
            <h2>Pending Updates</h2>
          </div>
          <span className="ns-count">{pending.length}</span>
        </div>

        <p className="ns-section-copy">
          Changed Notion pages wait here so they do not overwrite published
          content automatically.
        </p>

        {pending.length === 0 ? (
          <div className="ns-empty small">
            <strong>No pending updates</strong>
            <span>Your published articles are up to date.</span>
          </div>
        ) : (
          <div className="ns-pending-list">
            {pending.map((item) => {
              const isExpanded = expandedPendingId === item.id;
              const isResolving = resolvingId === item.id;

              return (
                <article className="ns-pending-card" key={item.id}>
                  <div className="ns-pending-head">
                    <div>
                      <h3>{item.proposed_title || item.previous_title}</h3>
                      <p>Changed in Notion: {item.notion_last_edited_time || '-'}</p>
                    </div>
                    <span className="ns-review-pill">Review</span>
                  </div>

                  <div className="ns-pending-actions">
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={() => setExpandedPendingId(isExpanded ? null : item.id)}
                    >
                      {isExpanded ? 'Hide Preview' : 'Review Changes'}
                    </button>
                    <button
                      type="button"
                      className="ns-btn secondary"
                      disabled={isResolving}
                      onClick={() => handleResolvePending(item.id, 'dismiss')}
                    >
                      {isResolving ? 'Working...' : 'Keep Current'}
                    </button>
                    <button
                      type="button"
                      className="ns-btn primary"
                      disabled={isResolving}
                      onClick={() => handleResolvePending(item.id, 'apply')}
                    >
                      {isResolving ? 'Working...' : 'Update to Latest'}
                    </button>
                  </div>

                  {isExpanded && (
                    <div className="ns-compare-grid">
                      <div className="ns-version-card current">
                        <div className="ns-version-label">Current</div>
                        <div
                          className="article-rich-content"
                          dangerouslySetInnerHTML={{ __html: item.previous_content || '' }}
                        />
                      </div>

                      <div className="ns-version-card proposed">
                        <div className="ns-version-label">From Notion</div>
                        <div
                          className="article-rich-content"
                          dangerouslySetInnerHTML={{ __html: item.proposed_content || '' }}
                        />
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="ns-card ns-history">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">History</span>
            <h2>Sync History</h2>
          </div>
          <span className="ns-count">{jobs.length}</span>
        </div>

        {jobs.length === 0 ? (
          <div className="ns-empty small">
            <strong>No sync history</strong>
            <span>Run your first Notion update check.</span>
          </div>
        ) : (
          <div className="ns-table-wrap">
            <table className="ns-table">
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
                      <span className={`ns-job-status ${job.status || 'unknown'}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{job.imported_count ?? 0}</td>
                    <td>{job.updated_count ?? 0}</td>
                    <td>{job.skipped_count ?? 0}</td>
                    <td>{job.failed_count ?? 0}</td>
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

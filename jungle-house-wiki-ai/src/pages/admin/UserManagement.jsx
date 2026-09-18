import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const NAV_ITEMS = [
  { key: 'all', label: 'All Users' },
  { key: 'pending', label: 'Pending' },
  { key: 'active', label: 'Active' },
  { key: 'history', label: 'Registration History' },
  { key: 'email', label: 'Email Test' },
];

function normalizeRole(roleValue) {
  const normalizedRole = String(roleValue || 'staff').toLowerCase().replace(/[\s_-]/g, '');
  return normalizedRole === 'teamlead' ? 'teamlead' : 'staff';
}

function formatRegistrationDate(value) {
  if (!value) return '-';
  const raw = String(value).trim();
  if (!raw) return '-';

  // The two User Management API endpoints supply ISO timestamps with UTC/offset.
  // Preserve unrecognised legacy values rather than silently inventing a timezone.
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kuching',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  }).formatToParts(parsed);
  const part = (type) => parts.find((item) => item.type === type)?.value || '';
  return `${part('day')}/${part('month')}/${part('year')} ${part('hour')}:${part('minute')} ${part('dayPeriod').toUpperCase()}`;
}

export default function UserManagement() {
  const { user } = useAuth();

  const actorRole = String(user?.role || '').toLowerCase().replace(/[\s_-]/g, '');
  const isManagerActor = actorRole === 'manager' || actorRole === 'admin';
  const isApproverActor = isManagerActor || actorRole === 'teamlead';

  const [users, setUsers] = useState([]);

  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const [activeView, setActiveView] = useState('all');
  const [search, setSearch] = useState('');

  const [message, setMessage] = useState('');
  const [emailTestMessage, setEmailTestMessage] = useState('');

  const [historyRecords, setHistoryRecords] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [historySearch, setHistorySearch] = useState('');

  const [emailTestLoading, setEmailTestLoading] = useState(false);
  const [testRecipient, setTestRecipient] = useState(user?.email || '');
  const [approvalDialog, setApprovalDialog] = useState({
    open: false,
    userId: null,
    fullName: '',
    email: '',
    role: 'staff',
  });

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/admin/users');
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Fetch users error:', error);
      setMessage(error.response?.data?.message || 'Unable to load users.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Load archived attempts for All Users as well as the dedicated History tab.
  const fetchHistory = useCallback(async () => {
    if (!isApproverActor) return;
    try {
      setHistoryLoading(true);
      setHistoryError('');
      const response = await api.get('/admin/registration-history');
      setHistoryRecords(Array.isArray(response.data?.records) ? response.data.records : []);
    } catch (error) {
      console.error('Fetch registration history error:', error);
      setHistoryRecords([]);
      setHistoryError(error.response?.data?.message || 'Unable to load registration history.');
    } finally {
      setHistoryLoading(false);
    }
  }, [isApproverActor]);

  useEffect(() => {
    if ((activeView === 'history' || activeView === 'all') && isApproverActor) {
      fetchHistory();
    }
  }, [activeView, fetchHistory, isApproverActor]);

  const filteredHistory = useMemo(() => {
    const keyword = historySearch.trim().toLowerCase();
    if (!keyword) return historyRecords;
    return historyRecords.filter((record) => [
      record.full_name, record.email, record.declined_by_name,
      record.decision_description, record.record_type,
    ].some((value) => String(value || '').toLowerCase().includes(keyword)));
  }, [historyRecords, historySearch]);

  const getDecisionReason = (record) => {
    const description = String(record.decision_description || '').trim();
    if (!description) return 'Not recorded';
    return description.replace(/^User ID \d+ registration declined\. Reason:\s*/i, '') || 'Not specified';
  };

  useEffect(() => {
    if (!approvalDialog.open) return undefined;

    const handleEscape = (event) => {
      if (event.key === 'Escape' && actionLoadingId !== approvalDialog.userId) {
        setApprovalDialog((prev) => ({ ...prev, open: false }));
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [approvalDialog.open, approvalDialog.userId, actionLoadingId]);

  // Show one login account, plus a separate read-only row for each past
  // application. The archived rows never participate in account actions.
  const archivedApplications = useMemo(() => (
    isApproverActor && !historyError
      ? historyRecords.filter((record) => record.record_type === 'archived').map((record) => ({
          user_id: record.user_id,
          history_id: record.history_id,
          full_name: record.full_name,
          email: record.email,
          role_name: null,
          status: 'declined',
          created_at: record.registered_at,
          isArchivedApplication: true,
        }))
      : []
  ), [historyRecords, historyError, isApproverActor]);

  const allUserRecords = useMemo(() => (
    [...users, ...archivedApplications]
  ), [users, archivedApplications]);

  const getStage = (item) => {
    if (item.status === 'pending') return 'pending';
    if (item.status === 'active') return 'active';
    if (item.status === 'inactive') return 'inactive';
    if (item.status === 'declined') return 'declined';
    return String(item.status || 'unknown').toLowerCase();
  };

  const counts = useMemo(() => ({
    all: allUserRecords.length,
    pending: users.filter((item) => getStage(item) === 'pending').length,
    active: users.filter((item) => getStage(item) === 'active').length,
  }), [users, allUserRecords]);

  const filteredUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    const records = activeView === 'all' ? allUserRecords : users;
    return records.filter((item) => {
      const stage = getStage(item);

      const viewMatches =
        activeView === 'all' ||
        (activeView === 'pending' && stage === 'pending') ||
        (activeView === 'active' && stage === 'active');

      if (!viewMatches) return false;
      if (!keyword) return true;

      return [item.full_name, item.email, item.role_name, stage]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [users, allUserRecords, activeView, search]);

  const updateUserStatus = async (userId, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';

    try {
      setActionLoadingId(userId);
      await api.put(`/admin/users/${userId}/status`, {
        status: newStatus,
      });
      setMessage(newStatus === 'active' ? 'User activated.' : 'User deactivated.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Unable to update user status.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const updateUserRole = async (userId, newRole) => {
    try {
      setActionLoadingId(userId);
      await api.put(`/admin/users/${userId}/role`, {
        role: newRole,
      });
      setMessage('Role updated.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || 'Unable to update role.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const openApprovalDialog = (item) => {
    if (!isApproverActor) return;
    setApprovalDialog({
      open: true,
      userId: item.user_id,
      fullName: item.full_name || 'User',
      email: item.email || '',
      role: normalizeRole(item.role_name),
    });
  };

  const closeApprovalDialog = () => {
    if (actionLoadingId === approvalDialog.userId) return;
    setApprovalDialog((prev) => ({ ...prev, open: false }));
  };

  const confirmApproveUser = async () => {
    if (!isApproverActor || !approvalDialog.userId) return;

    try {
      setActionLoadingId(approvalDialog.userId);
      setMessage('');

      const response = await api.put(
        `/admin/registration-requests/${approvalDialog.userId}/approve`,
        { role: approvalDialog.role }
      );

      if (response.data?.account_status && response.data.account_status !== 'active') {
        throw new Error('Approval was not confirmed. Please refresh the list and check this account.');
      }

      setMessage(response.data?.message || 'Registration approved. The user can now sign in.');
      setApprovalDialog((prev) => ({ ...prev, open: false }));
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || error.message || 'Approval failed.');
      await fetchUsers();
    } finally {
      setActionLoadingId(null);
    }
  };

  const declineUser = async (userId) => {
    if (!isApproverActor) return;
    const reason = window.prompt('Decline reason (optional)');
    if (reason === null) return;

    if (!window.confirm('Decline this registration? The account will remain in the audit history and cannot sign in.')) return;

    try {
      setActionLoadingId(userId);
      setMessage('');
      const response = await api.put(`/admin/registration-requests/${userId}/decline`, { reason });
      if (response.data?.account_status !== 'declined') {
        throw new Error('Decline was not confirmed. Please refresh the list and check this account.');
      }
      setMessage(response.data?.message || 'Registration declined. Account history preserved.');
      await fetchUsers();
    } catch (error) {
      setMessage(error.response?.data?.message || error.message || 'Decline failed.');
      await fetchUsers();
    } finally {
      setActionLoadingId(null);
    }
  };

  const testSystemEmail = async () => {
    if (!isApproverActor || !testRecipient.trim()) return;

    try {
      setEmailTestLoading(true);
      setEmailTestMessage('');

      const response = await api.post('/admin/email/test', {
        email: testRecipient.trim().toLowerCase(),
      });

      setEmailTestMessage(response.data?.message || 'Test email sent.');
    } catch (error) {
      setEmailTestMessage(error.response?.data?.message || 'Email test failed.');
    } finally {
      setEmailTestLoading(false);
    }
  };

  const getInitials = (name) => {
    return String(name || 'U')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
  };

  const stageLabel = (stage) => {
    if (stage === 'pending') return 'Pending';
    if (stage === 'active') return 'Active';
    if (stage === 'inactive') return 'Inactive';
    if (stage === 'declined') return 'Declined';
    return stage;
  };

  const isUserView = ['all', 'pending', 'active'].includes(activeView);

  return (
    <div className="user-management-page professional">
      <PageHeader title="User Management" subtitle="Staff accounts and access control." />

      <section className="um-summary-grid">
        <button
          type="button"
          className={`um-summary-card ${activeView === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveView('pending')}
        >
          <span className="um-summary-label">Pending</span>
          <strong>{counts.pending}</strong>
          <span className="um-summary-meta">Needs review</span>
        </button>

        <button
          type="button"
          className={`um-summary-card ${activeView === 'active' ? 'active' : ''}`}
          onClick={() => setActiveView('active')}
        >
          <span className="um-summary-label">Active</span>
          <strong>{counts.active}</strong>
          <span className="um-summary-meta">Can sign in</span>
        </button>

        <button
          type="button"
          className={`um-summary-card ${activeView === 'all' ? 'active' : ''}`}
          onClick={() => setActiveView('all')}
        >
          <span className="um-summary-label">Total</span>
          <strong>{counts.all}</strong>
          <span className="um-summary-meta">Accounts + past applications</span>
        </button>
      </section>

      <section className="um-workspace">
        <div className="um-workspace-head">
          <nav className="um-nav" aria-label="User management sections">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={activeView === item.key ? 'active' : ''}
                onClick={() => {
                  setActiveView(item.key);
                  setMessage('');
                  setEmailTestMessage('');
                }}
              >
                {item.label}
                {item.key === 'pending' && counts.pending > 0 ? (
                  <span className="um-nav-count">{counts.pending}</span>
                ) : null}
              </button>
            ))}
          </nav>

          {activeView === 'history' && isApproverActor ? (
            <input
              className="um-search"
              type="search"
              value={historySearch}
              onChange={(event) => setHistorySearch(event.target.value)}
              placeholder="Search registration history"
              aria-label="Search registration history"
            />
          ) : null}

          {isUserView ? (
            <input
              className="um-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name or email"
              aria-label="Search users"
            />
          ) : null}
        </div>

        {message && isUserView ? (
          <div className="um-feedback">{message}</div>
        ) : null}
        {activeView === 'all' && historyError ? (
          <div className="um-feedback" role="alert">
            Current users are shown, but past applications could not be loaded. {historyError}
          </div>
        ) : null}

        {isUserView ? (
          <>
            {loading ? (
              <div className="um-empty-state">Loading users...</div>
            ) : filteredUsers.length === 0 ? (
              <div className="um-empty-state">
                <strong>No users found</strong>
                <span>Try another filter or search.</span>
              </div>
            ) : (
              <div className="um-table-wrap">
                <table className="um-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th>Action</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredUsers.map((item) => {
                      const isManager =
                        String(item.role_name || '').toLowerCase() === 'manager';
                      const isPending = item.status === 'pending';
                      const isBusy = actionLoadingId === item.user_id;
                      const stage = getStage(item);

                      return (
                        <tr key={item.isArchivedApplication ? `history-${item.history_id}` : `user-${item.user_id}`}>
                          <td>
                            <div className="um-user">
                              <div className="um-avatar">{getInitials(item.full_name)}</div>
                              <div className="um-user-copy">
                                <strong>{item.full_name}</strong>
                                <span>{item.email}</span>
                                {item.isArchivedApplication ? (
                                  <span style={{ fontSize: '12px', color: '#9a6700' }}>Previous application · record only</span>
                                ) : null}
                              </div>
                            </div>
                          </td>

                          <td>
                            {item.isArchivedApplication ? (
                              <span className="um-muted">—</span>
                            ) : isManager ? (
                              <span className="um-role-tag manager">Manager</span>
                            ) : isManagerActor ? (
                              <select
                                className="um-role-select"
                                value={item.role_name}
                                onChange={(event) =>
                                  updateUserRole(item.user_id, event.target.value)
                                }
                                disabled={isBusy}
                              >
                                <option value="staff">Staff</option>
                                <option value="teamlead">Team Lead</option>
                              </select>
                            ) : (
                              <span className="um-role-tag">{item.role_name}</span>
                            )}
                          </td>

                          <td>
                            <span className={`um-status-tag ${stage}`}>
                              <i />
                              {stageLabel(stage)}
                            </span>
                          </td>

                          <td>
                            <span className="um-date">{formatRegistrationDate(item.created_at)}</span>
                          </td>

                          <td>
                            <div className="um-row-actions">
                              {item.isArchivedApplication ? (
                                <button
                                  type="button"
                                  className="um-action-btn secondary"
                                  onClick={() => {
                                    setHistorySearch(item.email || '');
                                    setActiveView('history');
                                  }}
                                >
                                  View history
                                </button>
                              ) : isManager ? (
                                <span className="um-protected">Protected</span>
                              ) : isPending && isApproverActor ? (
                                <>
                                  <button
                                    type="button"
                                    className="um-action-btn primary"
                                    disabled={isBusy}
                                    onClick={() => openApprovalDialog(item)}
                                  >
                                    {isBusy ? 'Working...' : 'Approve'}
                                  </button>
                                  <button
                                    type="button"
                                    className="um-action-btn danger"
                                    disabled={isBusy}
                                    onClick={() => declineUser(item.user_id)}
                                  >
                                    Decline
                                  </button>
                                </>
                              ) : item.status === 'declined' ? (
                                <span className="um-muted">—</span>
                              ) : isManagerActor ? (
                                <button
                                  type="button"
                                  className={`um-action-btn ${
                                    item.status === 'active' ? 'danger-soft' : 'secondary'
                                  }`}
                                  disabled={isBusy}
                                  onClick={() =>
                                    updateUserStatus(item.user_id, item.status)
                                  }
                                >
                                  {item.status === 'active' ? 'Deactivate' : 'Activate'}
                                </button>
                              ) : (
                                <span className="um-muted">—</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : null}

        {activeView === 'history' && isApproverActor ? (
          <div className="um-tool-panel">
            <div className="um-tool-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                <span className="um-tool-kicker">Registration Records</span>
                <h3 style={{ marginBottom: '4px' }}>Declined application history</h3>
                <p style={{ margin: 0, fontSize: '14px', color: '#64748b' }}>
                  Previous decisions stay on record even if the same email registers again.
                </p>
              </div>
              <button
                type="button"
                className="um-action-btn secondary"
                onClick={fetchHistory}
                disabled={historyLoading}
              >
                {historyLoading ? 'Refreshing...' : 'Refresh history'}
              </button>
            </div>

            {historyError ? (
              <div className="um-feedback" role="alert">{historyError}</div>
            ) : null}

            {historyLoading && historyRecords.length === 0 ? (
              <div className="um-empty-state">Loading registration history...</div>
            ) : historyError ? null : filteredHistory.length === 0 ? (
              <div className="um-empty-state">
                <strong>No declined applications found</strong>
                <span>Past declined applications will appear here when available.</span>
              </div>
            ) : (
              <div className="um-table-wrap">
                <table className="um-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Record</th>
                      <th>Registered</th>
                      <th>Declined</th>
                      <th>Reviewed by</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredHistory.map((record) => (
                      <tr key={`${record.record_type}-${record.history_id ?? record.user_id}`}>
                        <td>
                          <div className="um-user">
                            <div className="um-avatar">{getInitials(record.full_name)}</div>
                            <div className="um-user-copy">
                              <strong>{record.full_name || '-'}</strong>
                              <span>{record.email || '-'}</span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`um-status-tag ${record.record_type === 'archived' ? 'inactive' : 'declined'}`}>
                            <i />
                            {record.record_type === 'archived' ? 'Archived' : 'Declined'}
                          </span>
                        </td>
                        <td><span className="um-date">{formatRegistrationDate(record.registered_at)}</span></td>
                        <td><span className="um-date">{formatRegistrationDate(record.declined_at)}</span></td>
                        <td>{record.declined_by_name || 'Not recorded'}</td>
                        <td style={{ maxWidth: '320px', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                          {getDecisionReason(record)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}

        {activeView === 'email' ? (
          <div className="um-tool-panel">
            <div className="um-tool-head">
              <div>
                <span className="um-tool-kicker">System Email</span>
                <h3>Send test email</h3>
              </div>
            </div>

            <div className="um-email-form">
              <input
                type="email"
                value={testRecipient}
                onChange={(event) => {
                  setTestRecipient(event.target.value);
                  setEmailTestMessage('');
                }}
                placeholder="Recipient email"
              />

              <button
                type="button"
                className="um-action-btn primary"
                onClick={testSystemEmail}
                disabled={
                  emailTestLoading || !isApproverActor || !testRecipient.trim()
                }
              >
                {emailTestLoading ? 'Sending...' : 'Send Test'}
              </button>
            </div>

            {emailTestMessage ? (
              <div className="um-feedback">{emailTestMessage}</div>
            ) : null}
          </div>
        ) : null}
      </section>

      {approvalDialog.open ? (
        <div
          role="presentation"
          onClick={closeApprovalDialog}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.42)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 1200,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="approve-user-dialog-title"
            onClick={(event) => event.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: '560px',
              background: '#ffffff',
              borderRadius: '24px',
              boxShadow: '0 28px 70px rgba(15, 23, 42, 0.18)',
              border: '1px solid rgba(217, 119, 6, 0.16)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '24px 24px 18px',
                borderBottom: '1px solid rgba(226, 232, 240, 0.9)',
                background: 'linear-gradient(180deg, rgba(255, 251, 235, 0.95), rgba(255, 255, 255, 0.98))',
              }}
            >
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '6px 12px',
                  borderRadius: '999px',
                  fontSize: '12px',
                  fontWeight: 700,
                  letterSpacing: '0.03em',
                  color: '#b45309',
                  background: '#fef3c7',
                  marginBottom: '12px',
                }}
              >
                Registration Review
              </span>
              <h3
                id="approve-user-dialog-title"
                style={{ margin: 0, fontSize: '24px', lineHeight: 1.2, color: '#1f2937' }}
              >
                Approve this user?
              </h3>
              <p style={{ margin: '10px 0 0', color: '#6b7280', fontSize: '15px', lineHeight: 1.6 }}>
                Once approved, this account becomes <strong style={{ color: '#166534' }}>active</strong>{' '}
                and the user can sign in immediately.
              </p>
            </div>

            <div style={{ padding: '22px 24px 24px' }}>
              <div
                style={{
                  display: 'grid',
                  gap: '14px',
                  marginBottom: '18px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '14px',
                    padding: '14px 16px',
                    borderRadius: '18px',
                    background: '#f8fafc',
                    border: '1px solid #e5e7eb',
                  }}
                >
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '16px',
                      background: 'linear-gradient(135deg, #fbbf24, #d97706)',
                      color: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                      fontSize: '16px',
                      flexShrink: 0,
                    }}
                  >
                    {getInitials(approvalDialog.fullName)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, color: '#111827', fontSize: '16px' }}>
                      {approvalDialog.fullName}
                    </div>
                    <div style={{ color: '#6b7280', fontSize: '14px', wordBreak: 'break-word' }}>
                      {approvalDialog.email}
                    </div>
                  </div>
                </div>

                <label style={{ display: 'grid', gap: '8px' }}>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#374151' }}>
                    Account role
                  </span>
                  <select
                    value={approvalDialog.role}
                    onChange={(event) =>
                      setApprovalDialog((prev) => ({ ...prev, role: event.target.value }))
                    }
                    disabled={actionLoadingId === approvalDialog.userId}
                    style={{
                      width: '100%',
                      borderRadius: '14px',
                      border: '1px solid #d1d5db',
                      padding: '12px 14px',
                      fontSize: '15px',
                      color: '#111827',
                      background: '#ffffff',
                      outline: 'none',
                    }}
                  >
                    <option value="staff">Staff</option>
                    <option value="teamlead">Team Lead</option>
                  </select>
                </label>

                <div
                  style={{
                    borderRadius: '16px',
                    background: '#fffbeb',
                    border: '1px solid #fde68a',
                    padding: '14px 16px',
                    color: '#92400e',
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: '8px' }}>Approval summary</div>
                  <ul style={{ margin: 0, paddingLeft: '18px', lineHeight: 1.7, fontSize: '14px' }}>
                    <li>The account status will change from Pending to Active.</li>
                    <li>The user will be able to log in immediately after approval.</li>
                    <li>Assigned role will control access to pages and features.</li>
                  </ul>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '12px',
                  flexWrap: 'wrap',
                }}
              >
                <button
                  type="button"
                  onClick={closeApprovalDialog}
                  disabled={actionLoadingId === approvalDialog.userId}
                  style={{
                    minWidth: '120px',
                    borderRadius: '14px',
                    border: '1px solid #d1d5db',
                    background: '#ffffff',
                    color: '#374151',
                    padding: '12px 18px',
                    fontWeight: 600,
                    cursor: actionLoadingId === approvalDialog.userId ? 'not-allowed' : 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmApproveUser}
                  disabled={actionLoadingId === approvalDialog.userId}
                  style={{
                    minWidth: '160px',
                    borderRadius: '14px',
                    border: 'none',
                    background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                    color: '#ffffff',
                    padding: '12px 18px',
                    fontWeight: 700,
                    boxShadow: '0 12px 24px rgba(217, 119, 6, 0.22)',
                    cursor: actionLoadingId === approvalDialog.userId ? 'not-allowed' : 'pointer',
                  }}
                >
                  {actionLoadingId === approvalDialog.userId ? 'Approving...' : 'Approve User'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

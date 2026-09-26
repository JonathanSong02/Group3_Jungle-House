import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import './styles/UserManagement.css';

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
  const [roleFilter, setRoleFilter] = useState('all');

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
      setMessage('');
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
    if (activeView === 'history' && isApproverActor) {
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

  const getStage = (item) => {
    if (item.status === 'pending') return 'pending';
    if (item.status === 'active') return 'active';
    if (item.status === 'inactive') return 'inactive';
    if (item.status === 'declined') return 'declined';
    return String(item.status || 'unknown').toLowerCase();
  };

  const counts = useMemo(() => {
    const currentAccounts = users.filter((item) => getStage(item) !== 'declined');
    return {
      all: currentAccounts.length,
      pending: currentAccounts.filter((item) => getStage(item) === 'pending').length,
      active: currentAccounts.filter((item) => getStage(item) === 'active').length,
      inactive: currentAccounts.filter((item) => getStage(item) === 'inactive').length,
    };
  }, [users]);

  const matchesSearch = useCallback((item, keyword) => {
    if (!keyword) return true;
    return [item.full_name, item.email, item.role_name, getStage(item)]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword));
  }, []);

  const pendingUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return users.filter((item) => (
      getStage(item) === 'pending' &&
      matchesSearch(item, keyword)
    ));
  }, [users, search, matchesSearch]);

  const directoryUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return users.filter((item) => {
      const stage = getStage(item);

      // Pending registrations are intentionally separated into the review queue.
      // Declined applications belong in Registration History.
      if (stage === 'pending' || stage === 'declined') return false;
      if (activeView === 'active' && stage !== 'active') return false;

      const normalizedRole = String(item.role_name || '').toLowerCase().replace(/[\s_-]/g, '');
      if (roleFilter !== 'all' && normalizedRole !== roleFilter) return false;

      return matchesSearch(item, keyword);
    });
  }, [users, activeView, search, roleFilter, matchesSearch]);

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

  const isDirectoryView = activeView === 'all' || activeView === 'active';
  const showReviewQueue = activeView === 'all' || activeView === 'pending';

  const renderUserAvatar = (name, className = '') => (
    <span className={`um2-avatar ${className}`.trim()} aria-hidden="true">
      {getInitials(name)}
    </span>
  );

  return (
    <div className="user-management-page um2-page">
      <PageHeader title="User Management" subtitle="Review access requests and manage staff accounts." />

      <section className="um2-overview" aria-label="User account overview">
        <button
          type="button"
          className={`um2-stat ${activeView === 'all' ? 'selected' : ''}`}
          onClick={() => setActiveView('all')}
        >
          <span className="um2-stat-icon users" aria-hidden="true">U</span>
          <span>
            <small>Total accounts</small>
            <strong>{loading ? '—' : counts.all}</strong>
          </span>
        </button>

        <button
          type="button"
          className={`um2-stat ${activeView === 'active' ? 'selected' : ''}`}
          onClick={() => setActiveView('active')}
        >
          <span className="um2-stat-icon active" aria-hidden="true">✓</span>
          <span>
            <small>Active staff</small>
            <strong>{loading ? '—' : counts.active}</strong>
          </span>
        </button>

        <button
          type="button"
          className={`um2-stat attention ${activeView === 'pending' ? 'selected' : ''}`}
          onClick={() => setActiveView('pending')}
        >
          <span className="um2-stat-icon pending" aria-hidden="true">!</span>
          <span>
            <small>Needs review</small>
            <strong>{loading ? '—' : counts.pending}</strong>
          </span>
          {counts.pending > 0 ? <span className="um2-attention-dot" aria-label="Pending registrations" /> : null}
        </button>
      </section>

      <section className="um2-shell">
        <div className="um2-shell-top">
          <nav className="um2-tabs" aria-label="User management sections">
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
                  <span className="um2-tab-count">{counts.pending}</span>
                ) : null}
              </button>
            ))}
          </nav>

          {(isDirectoryView || activeView === 'pending') ? (
            <div className="um2-search-wrap">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search staff"
                aria-label="Search users"
              />
            </div>
          ) : null}

          {activeView === 'history' && isApproverActor ? (
            <div className="um2-search-wrap">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                value={historySearch}
                onChange={(event) => setHistorySearch(event.target.value)}
                placeholder="Search history"
                aria-label="Search registration history"
              />
            </div>
          ) : null}
        </div>

        {message && (isDirectoryView || activeView === 'pending') ? (
          <div className="um2-feedback" role="status">{message}</div>
        ) : null}

        {(isDirectoryView || activeView === 'pending') && loading ? (
          <div className="um2-loading-grid" aria-label="Loading users">
            <span /><span /><span />
          </div>
        ) : null}

        {!loading && showReviewQueue ? (
          <section className="um2-section um2-review-section">
            <div className="um2-section-heading">
              <div>
                <div className="um2-heading-line">
                  <h2>Needs Review</h2>
                  <span className={`um2-count-pill ${counts.pending > 0 ? 'has-items' : ''}`}>
                    {counts.pending}
                  </span>
                </div>
                <p>New account requests waiting for approval.</p>
              </div>

              {activeView === 'all' && counts.pending > 0 ? (
                <button
                  type="button"
                  className="um2-text-action"
                  onClick={() => setActiveView('pending')}
                >
                  Review all
                  <span aria-hidden="true">→</span>
                </button>
              ) : null}
            </div>

            {pendingUsers.length === 0 ? (
              <div className="um2-clear-state">
                <span className="um2-clear-icon" aria-hidden="true">✓</span>
                <div>
                  <strong>No registrations waiting</strong>
                  <p>{search ? 'No pending account matches your search.' : 'You are all caught up.'}</p>
                </div>
              </div>
            ) : (
              <div className="um2-review-grid">
                {pendingUsers.map((item) => {
                  const isBusy = actionLoadingId === item.user_id;

                  return (
                    <article className="um2-review-card" key={`pending-${item.user_id}`}>
                      <div className="um2-review-person">
                        {renderUserAvatar(item.full_name, 'pending')}
                        <div>
                          <strong>{item.full_name || 'Unnamed user'}</strong>
                          <span>{item.email}</span>
                        </div>
                        <span className="um2-status pending">Pending</span>
                      </div>

                      <div className="um2-review-meta">
                        <div>
                          <span>Requested role</span>
                          <strong>{normalizeRole(item.role_name) === 'teamlead' ? 'Team Lead' : 'Staff'}</strong>
                        </div>
                        <div>
                          <span>Registered</span>
                          <strong>{formatRegistrationDate(item.created_at)}</strong>
                        </div>
                      </div>

                      <div className="um2-review-actions">
                        <button
                          type="button"
                          className="um2-btn approve"
                          disabled={isBusy}
                          onClick={() => openApprovalDialog(item)}
                        >
                          {isBusy ? 'Working...' : 'Approve'}
                        </button>
                        <button
                          type="button"
                          className="um2-btn decline"
                          disabled={isBusy}
                          onClick={() => declineUser(item.user_id)}
                        >
                          Decline
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        ) : null}

        {!loading && isDirectoryView ? (
          <section className="um2-section um2-directory-section">
            <div className="um2-directory-head">
              <div>
                <h2>{activeView === 'active' ? 'Active Staff' : 'Staff Directory'}</h2>
                <p>{activeView === 'active' ? 'Accounts that can currently sign in.' : 'Manage roles and account access.'}</p>
              </div>

              <div className="um2-filter-row">
                <label className="um2-filter">
                  <span>Role</span>
                  <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                    <option value="all">All roles</option>
                    <option value="staff">Staff</option>
                    <option value="teamlead">Team Lead</option>
                    <option value="manager">Manager</option>
                  </select>
                </label>
                <button type="button" className="um2-refresh" onClick={fetchUsers} disabled={loading}>
                  Refresh
                </button>
              </div>
            </div>

            {directoryUsers.length === 0 ? (
              <div className="um2-empty">
                <strong>No staff found</strong>
                <span>Try another search or role filter.</span>
              </div>
            ) : (
              <div className="um2-table-wrap">
                <table className="um2-table">
                  <thead>
                    <tr>
                      <th>Staff member</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th className="um2-action-column">Access</th>
                    </tr>
                  </thead>
                  <tbody>
                    {directoryUsers.map((item) => {
                      const isManager =
                        String(item.role_name || '').toLowerCase() === 'manager';
                      const isBusy = actionLoadingId === item.user_id;
                      const stage = getStage(item);

                      return (
                        <tr key={`user-${item.user_id}`}>
                          <td>
                            <div className="um2-person-cell">
                              {renderUserAvatar(item.full_name)}
                              <div>
                                <strong>{item.full_name}</strong>
                                <span>{item.email}</span>
                              </div>
                            </div>
                          </td>
                          <td>
                            {isManager ? (
                              <span className="um2-role manager">Manager</span>
                            ) : isManagerActor ? (
                              <select
                                className="um2-role-select"
                                value={normalizeRole(item.role_name)}
                                onChange={(event) => updateUserRole(item.user_id, event.target.value)}
                                disabled={isBusy}
                                aria-label={`Role for ${item.full_name}`}
                              >
                                <option value="staff">Staff</option>
                                <option value="teamlead">Team Lead</option>
                              </select>
                            ) : (
                              <span className="um2-role">
                                {normalizeRole(item.role_name) === 'teamlead' ? 'Team Lead' : 'Staff'}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`um2-status ${stage}`}>
                              <i aria-hidden="true" />
                              {stageLabel(stage)}
                            </span>
                          </td>
                          <td>
                            <span className="um2-date">{formatRegistrationDate(item.created_at)}</span>
                          </td>
                          <td className="um2-action-column">
                            {isManager ? (
                              <span className="um2-protected">Protected</span>
                            ) : isManagerActor ? (
                              <button
                                type="button"
                                className={`um2-access-btn ${item.status === 'active' ? 'deactivate' : 'activate'}`}
                                disabled={isBusy}
                                onClick={() => updateUserStatus(item.user_id, item.status)}
                              >
                                {isBusy
                                  ? 'Updating...'
                                  : item.status === 'active'
                                    ? 'Deactivate'
                                    : 'Activate'}
                              </button>
                            ) : (
                              <span className="um2-muted">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : null}

        {activeView === 'history' && isApproverActor ? (
          <section className="um2-section um2-history-section">
            <div className="um2-directory-head">
              <div>
                <h2>Registration History</h2>
                <p>Declined and archived applications are kept here for audit reference.</p>
              </div>
              <button
                type="button"
                className="um2-refresh"
                onClick={fetchHistory}
                disabled={historyLoading}
              >
                {historyLoading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>

            {historyError ? (
              <div className="um2-feedback danger" role="alert">{historyError}</div>
            ) : null}

            {historyLoading && historyRecords.length === 0 ? (
              <div className="um2-loading-grid"><span /><span /><span /></div>
            ) : historyError ? null : filteredHistory.length === 0 ? (
              <div className="um2-empty">
                <strong>No registration history</strong>
                <span>Declined applications will appear here.</span>
              </div>
            ) : (
              <div className="um2-table-wrap">
                <table className="um2-table history">
                  <thead>
                    <tr>
                      <th>Applicant</th>
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
                          <div className="um2-person-cell">
                            {renderUserAvatar(record.full_name)}
                            <div>
                              <strong>{record.full_name || '-'}</strong>
                              <span>{record.email || '-'}</span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`um2-status ${record.record_type === 'archived' ? 'inactive' : 'declined'}`}>
                            <i aria-hidden="true" />
                            {record.record_type === 'archived' ? 'Archived' : 'Declined'}
                          </span>
                        </td>
                        <td><span className="um2-date">{formatRegistrationDate(record.registered_at)}</span></td>
                        <td><span className="um2-date">{formatRegistrationDate(record.declined_at)}</span></td>
                        <td>{record.declined_by_name || 'Not recorded'}</td>
                        <td className="um2-reason">{getDecisionReason(record)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : null}

        {activeView === 'email' ? (
          <section className="um2-section um2-email-section">
            <div className="um2-email-card">
              <div className="um2-email-icon" aria-hidden="true">✉</div>
              <div className="um2-email-copy">
                <span>System Email</span>
                <h2>Send a test email</h2>
                <p>Use this only to confirm that the configured email service is working.</p>
              </div>

              <div className="um2-email-form">
                <input
                  type="email"
                  value={testRecipient}
                  onChange={(event) => {
                    setTestRecipient(event.target.value);
                    setEmailTestMessage('');
                  }}
                  placeholder="Recipient email"
                  aria-label="Recipient email"
                />
                <button
                  type="button"
                  className="um2-btn approve"
                  onClick={testSystemEmail}
                  disabled={emailTestLoading || !isApproverActor || !testRecipient.trim()}
                >
                  {emailTestLoading ? 'Sending...' : 'Send test'}
                </button>
              </div>

              {emailTestMessage ? (
                <div className="um2-feedback email">{emailTestMessage}</div>
              ) : null}
            </div>
          </section>
        ) : null}
      </section>

      {approvalDialog.open ? (
        <div className="um2-modal-backdrop" role="presentation" onClick={closeApprovalDialog}>
          <div
            className="um2-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approve-user-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="um2-modal-head">
              <span className="um2-modal-kicker">Registration Review</span>
              <h3 id="approve-user-dialog-title">Approve account</h3>
              <p>Choose the account role before allowing this user to sign in.</p>
            </div>

            <div className="um2-modal-body">
              <div className="um2-modal-user">
                {renderUserAvatar(approvalDialog.fullName, 'pending')}
                <div>
                  <strong>{approvalDialog.fullName}</strong>
                  <span>{approvalDialog.email}</span>
                </div>
              </div>

              <label className="um2-modal-field">
                <span>Account role</span>
                <select
                  value={approvalDialog.role}
                  onChange={(event) =>
                    setApprovalDialog((prev) => ({ ...prev, role: event.target.value }))
                  }
                  disabled={actionLoadingId === approvalDialog.userId}
                >
                  <option value="staff">Staff</option>
                  <option value="teamlead">Team Lead</option>
                </select>
              </label>

              <div className="um2-modal-note">
                <strong>After approval</strong>
                <span>The account becomes active and the user can sign in immediately.</span>
              </div>
            </div>

            <div className="um2-modal-actions">
              <button
                type="button"
                className="um2-btn cancel"
                onClick={closeApprovalDialog}
                disabled={actionLoadingId === approvalDialog.userId}
              >
                Cancel
              </button>
              <button
                type="button"
                className="um2-btn approve"
                onClick={confirmApproveUser}
                disabled={actionLoadingId === approvalDialog.userId}
              >
                {actionLoadingId === approvalDialog.userId ? 'Approving...' : 'Approve user'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

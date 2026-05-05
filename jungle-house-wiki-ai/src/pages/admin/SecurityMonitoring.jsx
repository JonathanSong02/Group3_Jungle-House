import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

export default function SecurityMonitoring() {
  const [activeTab, setActiveTab] = useState('login');

  const [loginHistory, setLoginHistory] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const [loginPage, setLoginPage] = useState(1);
  const [auditPage, setAuditPage] = useState(1);

  const rowsPerPage = 10;

  const fetchSecurityData = async () => {
    try {
      setLoading(true);
      setError('');

      const [loginResponse, auditResponse] = await Promise.all([
        api.get('/security/login-history'),
        api.get('/security/audit-logs'),
      ]);

      setLoginHistory(loginResponse.data.login_history || []);
      setAuditLogs(auditResponse.data.audit_logs || []);
    } catch (err) {
      console.error('SECURITY MONITORING ERROR:', err);
      setError(err.response?.data?.message || 'Unable to load security monitoring data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSecurityData();
  }, []);

  useEffect(() => {
    setLoginPage(1);
    setAuditPage(1);
  }, [searchText, statusFilter, activeTab]);

  const formatStatus = (status) => {
    if (status === 'success') return 'Success';
    if (status === 'failed') return 'Failed';
    return status || '-';
  };

  const successCount = loginHistory.filter((log) => log.status === 'success').length;
  const failedCount = loginHistory.filter((log) => log.status === 'failed').length;

  const filteredLoginHistory = useMemo(() => {
    return loginHistory.filter((log) => {
      const search = searchText.toLowerCase();

      const matchesSearch =
        String(log.user || '').toLowerCase().includes(search) ||
        String(log.email || '').toLowerCase().includes(search) ||
        String(log.ip_address || '').toLowerCase().includes(search);

      const matchesStatus =
        statusFilter === 'all' || log.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [loginHistory, searchText, statusFilter]);

  const filteredAuditLogs = useMemo(() => {
    return auditLogs.filter((log) => {
      const search = searchText.toLowerCase();

      return (
        String(log.action || '').toLowerCase().includes(search) ||
        String(log.module || '').toLowerCase().includes(search) ||
        String(log.actor || '').toLowerCase().includes(search) ||
        String(log.description || '').toLowerCase().includes(search)
      );
    });
  }, [auditLogs, searchText]);

  const paginate = (items, page) => {
    const startIndex = (page - 1) * rowsPerPage;
    return items.slice(startIndex, startIndex + rowsPerPage);
  };

  const totalLoginPages = Math.ceil(filteredLoginHistory.length / rowsPerPage) || 1;
  const totalAuditPages = Math.ceil(filteredAuditLogs.length / rowsPerPage) || 1;

  const loginRows = paginate(filteredLoginHistory, loginPage);
  const auditRows = paginate(filteredAuditLogs, auditPage);

  const Pagination = ({ currentPage, totalPages, onPrevious, onNext }) => {
    return (
      <div
        className="row-between"
        style={{
          marginTop: '1rem',
          paddingTop: '1rem',
          borderTop: '1px solid rgba(0,0,0,0.08)',
        }}
      >
        <p className="muted" style={{ margin: 0 }}>
          Page {currentPage} of {totalPages}
        </p>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            className="secondary-btn"
            onClick={onPrevious}
            disabled={currentPage <= 1}
          >
            Previous
          </button>

          <button
            type="button"
            className="secondary-btn"
            onClick={onNext}
            disabled={currentPage >= totalPages}
          >
            Next
          </button>
        </div>
      </div>
    );
  };

  const renderToolbar = () => {
    return (
      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '2fr 1fr auto',
            gap: '1rem',
            alignItems: 'end',
          }}
        >
          <div>
            <label className="form-label">Search</label>
            <input
              type="text"
              placeholder={
                activeTab === 'login'
                  ? 'Search user, email, or IP address...'
                  : 'Search action, module, actor, or description...'
              }
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </div>

          {activeTab === 'login' ? (
            <div>
              <label className="form-label">Status</label>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">All Status</option>
                <option value="success">Success</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          ) : (
            <div>
              <label className="form-label">Type</label>
              <select disabled>
                <option>All Audit Logs</option>
              </select>
            </div>
          )}

          <button
            type="button"
            className="secondary-btn"
            onClick={fetchSecurityData}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </section>
    );
  };

  const renderSummaryCards = () => {
    return (
      <div className="three-column-grid" style={{ marginBottom: '1.5rem' }}>
        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Total Login Records
          </p>
          <h2 style={{ margin: 0 }}>{loginHistory.length}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Successful Logins
          </p>
          <h2 style={{ margin: 0 }}>{successCount}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Failed Logins
          </p>
          <h2 style={{ margin: 0 }}>{failedCount}</h2>
        </section>
      </div>
    );
  };

  const renderLoginHistory = () => {
    return (
      <section className="card-like table-card">
        <div className="row-between" style={{ marginBottom: '1rem' }}>
          <div>
            <h3>Login History</h3>
            <p className="muted">
              Showing {loginRows.length} of {filteredLoginHistory.length} matching records.
            </p>
          </div>
        </div>

        {filteredLoginHistory.length === 0 ? (
          <p className="muted">No login records found.</p>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Email</th>
                  <th>Time</th>
                  <th>Status</th>
                  <th>IP Address</th>
                </tr>
              </thead>

              <tbody>
                {loginRows.map((log) => (
                  <tr key={log.login_id}>
                    <td>{log.user || 'Unknown'}</td>
                    <td>{log.email || '-'}</td>
                    <td>{log.time || '-'}</td>
                    <td>
                      <span
                        className={
                          log.status === 'success'
                            ? 'status-pill status-resolved'
                            : 'status-pill status-pending'
                        }
                      >
                        {formatStatus(log.status)}
                      </span>
                    </td>
                    <td>{log.ip_address || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <Pagination
              currentPage={loginPage}
              totalPages={totalLoginPages}
              onPrevious={() => setLoginPage((prev) => Math.max(prev - 1, 1))}
              onNext={() => setLoginPage((prev) => Math.min(prev + 1, totalLoginPages))}
            />
          </>
        )}
      </section>
    );
  };

  const renderAuditLog = () => {
    return (
      <section className="card-like table-card">
        <div className="row-between" style={{ marginBottom: '1rem' }}>
          <div>
            <h3>Audit Log</h3>
            <p className="muted">
              Showing {auditRows.length} of {filteredAuditLogs.length} matching records.
            </p>
          </div>
        </div>

        {filteredAuditLogs.length === 0 ? (
          <p className="muted">No audit records found.</p>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Module</th>
                  <th>Actor</th>
                  <th>Description</th>
                  <th>Time</th>
                </tr>
              </thead>

              <tbody>
                {auditRows.map((log) => (
                  <tr key={log.audit_id}>
                    <td>{log.action || '-'}</td>
                    <td>{log.module || '-'}</td>
                    <td>{log.actor || 'System'}</td>
                    <td>{log.description || '-'}</td>
                    <td>{log.time || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <Pagination
              currentPage={auditPage}
              totalPages={totalAuditPages}
              onPrevious={() => setAuditPage((prev) => Math.max(prev - 1, 1))}
              onNext={() => setAuditPage((prev) => Math.min(prev + 1, totalAuditPages))}
            />
          </>
        )}
      </section>
    );
  };

  return (
    <div>
      <PageHeader
        title="Security / Monitoring"
        subtitle="Monitor login activity, audit records, and important system changes."
      />

      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <h3>Security / Monitoring Overview</h3>
        <p className="muted">
          This module supports system accountability and protection. It helps management identify
          suspicious or incorrect activity, improves trust in the platform, and is important for a
          system that contains internal company knowledge.
        </p>
      </section>

      {renderSummaryCards()}

      {error ? <p className="error-text">{error}</p> : null}

      <div
        className="tab-row"
        style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          className={activeTab === 'login' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('login')}
        >
          Login History
        </button>

        <button
          type="button"
          className={activeTab === 'audit' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('audit')}
        >
          Audit Log
        </button>
      </div>

      {renderToolbar()}

      {loading && loginHistory.length === 0 && auditLogs.length === 0 ? (
        <section className="card-like">
          <p className="muted">Loading security monitoring data...</p>
        </section>
      ) : (
        <>
          {activeTab === 'login' ? renderLoginHistory() : null}
          {activeTab === 'audit' ? renderAuditLog() : null}
        </>
      )}
    </div>
  );
}
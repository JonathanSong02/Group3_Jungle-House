import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateAuditAction, translateAuditModule } from '../../i18n/auditText';
import './styles/SecurityMonitoring.css';

export default function SecurityMonitoring() {
  const { t, tOr } = useLanguage();
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
      setError(err.response?.data?.message || t('sec.err.load'));
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
    return status ? tOr(`status.${status}`, status) : '-';
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

  const Pagination = ({ currentPage, totalPages, onPrevious, onNext }) => (
    <div className="sm-pagination">
      <span>{t('sec.pageOf', { page: currentPage, total: totalPages })}</span>

      <div>
        <button
          type="button"
          className="sm-btn"
          onClick={onPrevious}
          disabled={currentPage <= 1}
        >
          {t('common.previous')}
        </button>

        <button
          type="button"
          className="sm-btn"
          onClick={onNext}
          disabled={currentPage >= totalPages}
        >
          {t('common.next')}
        </button>
      </div>
    </div>
  );

  return (
    <div className="sm-page">
      <PageHeader
        title={t('sec.title')}
        subtitle={t('sec.subtitle')}
      />

      <section className="sm-summary-grid">
        <div className="sm-summary-card total">
          <span>{t('sec.loginRecords')}</span>
          <strong>{loginHistory.length}</strong>
        </div>

        <div className="sm-summary-card success">
          <span>{t('sec.successful')}</span>
          <strong>{successCount}</strong>
        </div>

        <div className="sm-summary-card failed">
          <span>{t('sec.failed')}</span>
          <strong>{failedCount}</strong>
        </div>

        <div className="sm-summary-card audit">
          <span>{t('sec.auditEvents')}</span>
          <strong>{auditLogs.length}</strong>
        </div>
      </section>

      {error ? <div className="sm-feedback">{error}</div> : null}

      <section className="sm-workspace">
        <div className="sm-workspace-head">
          <div className="sm-tabs">
            <button
              type="button"
              className={activeTab === 'login' ? 'active' : ''}
              onClick={() => setActiveTab('login')}
            >
              {t('sec.tab.login')}
              <span>{loginHistory.length}</span>
            </button>

            <button
              type="button"
              className={activeTab === 'audit' ? 'active' : ''}
              onClick={() => setActiveTab('audit')}
            >
              {t('sec.tab.audit')}
              <span>{auditLogs.length}</span>
            </button>
          </div>

          <div className="sm-tools">
            <input
              type="search"
              placeholder={activeTab === 'login' ? t('sec.searchLogin') : t('sec.searchAudit')}
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />

            {activeTab === 'login' ? (
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">{t('sec.allStatus')}</option>
                <option value="success">{t('status.success')}</option>
                <option value="failed">{t('status.failed')}</option>
              </select>
            ) : null}

            <button
              type="button"
              className="sm-btn refresh"
              onClick={fetchSecurityData}
              disabled={loading}
            >
              {loading ? t('an.refreshing') : t('an.refresh')}
            </button>
          </div>
        </div>

        {loading && loginHistory.length === 0 && auditLogs.length === 0 ? (
          <div className="sm-empty">
            <strong>{t('sec.loading')}</strong>
          </div>
        ) : activeTab === 'login' ? (
          filteredLoginHistory.length === 0 ? (
            <div className="sm-empty">
              <strong>{t('sec.noLogin')}</strong>
            </div>
          ) : (
            <>
              <div className="sm-table-wrap">
                <table className="sm-table">
                  <thead>
                    <tr>
                      <th>{t('sec.col.user')}</th>
                      <th>{t('sec.col.email')}</th>
                      <th>{t('sec.col.time')}</th>
                      <th>{t('sec.col.status')}</th>
                      <th>{t('sec.col.ip')}</th>
                    </tr>
                  </thead>

                  <tbody>
                    {loginRows.map((log) => (
                      <tr key={log.login_id}>
                        <td><strong>{log.user || t('sec.unknown')}</strong></td>
                        <td>{log.email || '-'}</td>
                        <td>{log.time || '-'}</td>
                        <td>
                          <span className={`sm-status ${log.status || 'unknown'}`}>
                            <i />
                            {formatStatus(log.status)}
                          </span>
                        </td>
                        <td><code>{log.ip_address || '-'}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                currentPage={loginPage}
                totalPages={totalLoginPages}
                onPrevious={() => setLoginPage((prev) => Math.max(prev - 1, 1))}
                onNext={() => setLoginPage((prev) => Math.min(prev + 1, totalLoginPages))}
              />
            </>
          )
        ) : filteredAuditLogs.length === 0 ? (
          <div className="sm-empty">
            <strong>{t('sec.noAudit')}</strong>
          </div>
        ) : (
          <>
            <div className="sm-table-wrap">
              <table className="sm-table">
                <thead>
                  <tr>
                    <th>{t('sec.col.action')}</th>
                    <th>{t('sec.col.module')}</th>
                    <th>{t('sec.col.actor')}</th>
                    <th>{t('sec.col.description')}</th>
                    <th>{t('sec.col.time')}</th>
                  </tr>
                </thead>

                <tbody>
                  {auditRows.map((log) => (
                    <tr key={log.audit_id}>
                      <td><strong>{translateAuditAction(t, log.action) || '-'}</strong></td>
                      <td><span className="sm-module">{translateAuditModule(t, log.module) || '-'}</span></td>
                      <td>{log.actor && log.actor !== 'System' ? log.actor : t('sec.system')}</td>
                      <td className="sm-description">{log.description || '-'}</td>
                      <td>{log.time || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={auditPage}
              totalPages={totalAuditPages}
              onPrevious={() => setAuditPage((prev) => Math.max(prev - 1, 1))}
              onNext={() => setAuditPage((prev) => Math.min(prev + 1, totalAuditPages))}
            />
          </>
        )}
      </section>
    </div>
  );
}

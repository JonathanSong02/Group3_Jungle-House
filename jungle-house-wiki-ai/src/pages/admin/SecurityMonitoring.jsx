import PageHeader from '../../components/PageHeader';

const loginHistory = [
  { id: 1, user: 'Aina Staff', time: '2026-04-01 09:30', status: 'Success' },
  { id: 2, user: 'Brandon Lead', time: '2026-04-01 10:12', status: 'Success' },
  { id: 3, user: 'Unknown', time: '2026-04-01 11:02', status: 'Failed' },
];

const auditLogs = [
  { id: 1, action: 'Edited article', actor: 'Cheryl Manager' },
  { id: 2, action: 'Submitted manual answer', actor: 'Brandon Lead' },
  { id: 3, action: 'Updated AI threshold', actor: 'Cheryl Manager' },
];

export default function SecurityMonitoring() {
  return (
    <div>
      <PageHeader
        title="Security / Monitoring"
        subtitle="Basic visibility into login history and audit records."
      />

      <div className="two-column-grid">
        <section className="card-like table-card">
          <h3>Login History</h3>
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Time</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loginHistory.map((log) => (
                <tr key={log.id}>
                  <td>{log.user}</td>
                  <td>{log.time}</td>
                  <td>{log.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card-like table-card">
          <h3>Audit Log</h3>
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Actor</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.id}>
                  <td>{log.action}</td>
                  <td>{log.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

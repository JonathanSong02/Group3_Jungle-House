export default function StatusBadge({ status }) {
  const tone = String(status || '').toLowerCase();
  return <span className={`status-badge ${tone}`}>{status}</span>;
}

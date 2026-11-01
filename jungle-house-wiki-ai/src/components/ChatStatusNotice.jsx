export default function ChatStatusNotice({ storageError, uploadError, onRetry, retrying = false, t }) {
  const message = storageError || uploadError;
  if (!message) return null;
  return (
    <div role="alert" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', marginBottom: '10px',
      padding: '10px 12px', borderRadius: '12px', border: '1px solid #efb0aa', backgroundColor: '#fff5f3',
      color: '#9f352d', fontSize: '13px', lineHeight: 1.45 }}>
      <span aria-hidden="true">⚠</span>
      <div style={{ flex: 1 }}>
        <strong style={{ display: 'block', marginBottom: '2px' }}>{t(storageError ? 'chat.storageUnavailableTitle' : 'chat.uploadRejected')}</strong>
        <span>{message}</span>
        {storageError && onRetry ? <button type="button" className="secondary-btn" style={{ marginLeft: '10px' }}
          onClick={onRetry} disabled={retrying}>{t(retrying ? 'common.loading' : 'chat.retryConnection')}</button> : null}
      </div>
    </div>
  );
}

import { useEffect, useRef } from 'react';
import { API_BASE_URL } from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';

import { MESSAGE_FILE_ACCEPT } from '../utils/messageAttachment';

export function MessageAttachment({ attachment, file }) {
  const { t } = useLanguage();
  const linkRef = useRef(null);
  const imageRef = useRef(null);
  useEffect(() => {
    if (!file) return undefined;
    const url = URL.createObjectURL(file);
    if (linkRef.current) linkRef.current.href = url;
    if (imageRef.current) imageRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const name = file?.name || attachment?.name;
  const type = file?.type || attachment?.type || '';
  const size = file?.size || attachment?.size || 0;
  // The server supplies private API references only; never render arbitrary URLs.
  const path = attachment?.url || '';
  const url = file ? '' : (/^\/api\/messages\/attachments\/[a-f0-9]{64}$/.test(path)
    ? `${API_BASE_URL.replace(/\/api$/, '')}${path}` : '');
  return <a ref={linkRef} className="messages-attachment-card" href={url || undefined} target="_blank" rel="noopener noreferrer">
    {type.startsWith('image/') && (file || url)
      ? <img ref={imageRef} src={url || undefined} alt={name} loading="lazy" />
      : <span className="messages-file-symbol" aria-hidden="true">▤</span>}
    <span className="messages-file-info"><strong>{name}</strong><small>{Math.max(1, Math.ceil(size / 1024))} KB · {t(type.startsWith('image/') ? 'msg.imageFile' : 'msg.documentFile')}</small></span>
  </a>;
}

export function MessageAttachmentPicker({ file, onSelect, onRemove, disabled }) {
  const { t, tOr } = useLanguage();
  return <div className="messages-attachment-picker">
    {file && <div className="messages-attachment-draft">
      <MessageAttachment file={file} />
      <button type="button" className="messages-remove-file" onClick={onRemove} disabled={disabled}
        aria-label={tOr('msg.removeAttachment', 'Remove attachment')}>×</button>
    </div>}
    <label className={`messages-attach-btn ${disabled ? 'disabled' : ''}`} title={t('chat.uploadTitle')}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L12 3a2 2 0 0 1 3 3L5 16" /></svg>
      <span>{t('chat.attachFile')}</span>
      <input type="file" accept={MESSAGE_FILE_ACCEPT} disabled={disabled} onChange={(event) => {
        const selected = event.target.files?.[0];
        if (selected) onSelect(selected);
        event.target.value = '';
      }} />
    </label>
    <small className="messages-attachment-hint">{tOr('msg.attachmentHint', 'Paste an image · Images, PDF, Word · Max 7MB')}</small>
  </div>;
}

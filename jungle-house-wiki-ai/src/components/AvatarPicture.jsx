import { useState } from 'react';

// Render only the normalized JPEG returned by our authenticated backend.
function Picture({ src, fallback }) {
  const [failed, setFailed] = useState(false);
  if (failed || typeof src !== 'string' || !src.startsWith('data:image/jpeg;base64,')) {
    return fallback;
  }
  return (
    <img src={src} alt="" draggable={false} onError={() => setFailed(true)}
      style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover', borderRadius: 'inherit', minWidth: 0, minHeight: 0 }} />
  );
}

export default function AvatarPicture({ src, fallback }) {
  return <Picture key={src || 'initial'} src={src} fallback={fallback} />;
}

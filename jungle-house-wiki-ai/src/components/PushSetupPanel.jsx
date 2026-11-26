import { useEffect, useState } from 'react';
import { disablePush, enablePush, pushLabels, pushState } from '../services/webPush';

// Turn "AI answer is ready" phone / browser notifications on or off, or
// explain what this device needs first (2026-11-26, step 2). Used on the
// Profile page and in the one-time question after the first AI request.
export default function PushSetupPanel({ t, compact = false, onChange }) {
  const [state, setState] = useState('loading');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    pushState().then((value) => { if (active) setState(value); });
    return () => { active = false; };
  }, []);

  const run = (action) => async () => {
    setBusy(true);
    setFailed(false);
    try {
      const next = await action();
      setState(next);
      onChange?.(next);
    } catch (error) {
      console.error('Notification setting error:', error);
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  if (state === 'loading') return null;

  return (
    <div className={`push-setup ${compact ? 'push-setup-compact' : ''}`}>
      {state === 'ios-install' ? (
        <>
          <p>{t('push.ios.intro')}</p>
          <ol className="push-setup-steps">
            <li>{t('push.ios.step1')}</li>
            <li>{t('push.ios.step2')}</li>
            <li>{t('push.ios.step3')}</li>
          </ol>
        </>
      ) : (
        <p>{t(`push.state.${state}`)}</p>
      )}
      {state === 'off' && (
        <button type="button" className="primary-btn push-setup-button" disabled={busy}
          onClick={run(() => enablePush(pushLabels(t)))}>
          {busy ? t('push.working') : t('push.turnOn')}
        </button>
      )}
      {state === 'on' && !compact && (
        <button type="button" className="secondary-btn push-setup-button" disabled={busy} onClick={run(disablePush)}>
          {busy ? t('push.working') : t('push.turnOff')}
        </button>
      )}
      {failed && <p className="push-setup-error" role="alert">{t('push.failed')}</p>}
    </div>
  );
}

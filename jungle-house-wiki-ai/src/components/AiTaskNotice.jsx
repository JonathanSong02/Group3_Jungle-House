import { useEffect, useRef, useState } from 'react';
import { aiTasks, useAiTasks } from '../services/aiTasks';
import { isLookingAt } from '../services/aiTaskManager';
import { promptDone, markPromptDone, pushLabels, pushState, refreshPush } from '../services/webPush';
import PushSetupPanel from './PushSetupPanel';

// "AI keeps running after the page is left" (2026-11-26).
// When an AI chat answer or AI quiz is ready and the staff member is not
// looking at it, a small box says so (no question or answer text, so nothing
// private shows on a shared screen) and the sidebar gets a dot until opened.
// A hidden browser tab also gets "✓" in its title. Also collects tasks that
// were still running when the page was reloaded.
// Step 2: asks once whether to turn on phone notifications, keeps this
// browser's notification subscription up to date, and opens the right chat
// when a notification is tapped.
const TITLE_MARK = '✓ ';
const AUTO_HIDE_MS = 10_000;

export default function AiTaskNotice({ userId, pathname, search, activeSessionId, onOpenChat, onOpenQuiz, t }) {
  const [notice, setNotice] = useState(null);
  const [askPush, setAskPush] = useState(false);
  const place = useRef({ pathname, activeSessionId });
  const openers = useRef({ onOpenChat, onOpenQuiz });
  useEffect(() => {
    place.current = { pathname, activeSessionId };
    openers.current = { onOpenChat, onOpenQuiz };
  }, [pathname, activeSessionId, onOpenChat, onOpenQuiz]);

  const running = useAiTasks().some((task) => String(task.userId) === String(userId));

  useEffect(() => {
    if (userId == null) return undefined;
    aiTasks.resume(userId);
    refreshPush(pushLabels(t));
    return aiTasks.onDone((event) => {
      if (String(event.userId) !== String(userId)) return;
      if (event.kind === 'quiz' && !event.ok) return; // the quiz page shows its own error
      const hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
      if (hidden && !document.title.startsWith(TITLE_MARK)) document.title = TITLE_MARK + document.title;
      if (isLookingAt(event, place.current)) return;
      aiTasks.addUnseen(userId, { kind: event.kind, sessionId: event.meta?.sessionId ?? null, requestId: event.requestId });
      setNotice({ kind: event.kind, sessionId: event.meta?.sessionId ?? null, id: event.requestId });
    });
  // Language changes are picked up on the next app start (refreshPush).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // First AI question on this device: ask once whether to notify the phone.
  useEffect(() => {
    if (!running || promptDone()) return undefined;
    let active = true;
    pushState().then((state) => {
      if (active && (state === 'off' || state === 'ios-install')) setAskPush(true);
    });
    return () => { active = false; };
  }, [running]);

  // A tapped notification while the site is open (sent by public/sw.js).
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.serviceWorker) return undefined;
    const handle = (event) => {
      if (event.data?.type !== 'jh-open-ai-task') return;
      if (event.data.kind === 'quiz') openers.current.onOpenQuiz();
      else openers.current.onOpenChat(event.data.sessionId);
    };
    navigator.serviceWorker.addEventListener('message', handle);
    return () => navigator.serviceWorker.removeEventListener('message', handle);
  }, []);

  // A tapped notification that opened the site: /chat?aiSession=<id>.
  useEffect(() => {
    const sessionId = new URLSearchParams(search || '').get('aiSession');
    if (sessionId && /^\d{1,20}$/.test(sessionId)) openers.current.onOpenChat(Number(sessionId));
  }, [search]);

  useEffect(() => {
    const clearMark = () => {
      if (document.visibilityState === 'visible' && document.title.startsWith(TITLE_MARK)) {
        document.title = document.title.slice(TITLE_MARK.length);
      }
    };
    document.addEventListener('visibilitychange', clearMark);
    return () => document.removeEventListener('visibilitychange', clearMark);
  }, []);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(null), AUTO_HIDE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const closePushQuestion = () => {
    markPromptDone();
    setAskPush(false);
  };

  // Opening the page yourself makes the box pointless.
  const showNotice = notice && !isLookingAt({ kind: notice.kind, meta: { sessionId: notice.sessionId } }, { pathname, activeSessionId });
  const open = () => {
    setNotice(null);
    if (notice.kind === 'chat') onOpenChat(notice.sessionId);
    else onOpenQuiz();
  };

  return (
    <>
      {showNotice && (
        <div className="ai-task-notice" role="status">
          <button type="button" className="ai-task-notice-open" onClick={open}>
            <span className="ai-task-notice-title">✓ {t(notice.kind === 'quiz' ? 'aiTask.doneQuiz' : 'aiTask.doneChat')}</span>
            <span className="ai-task-notice-action">{t('aiTask.view')}</span>
          </button>
          <button type="button" className="ai-task-notice-close" aria-label={t('aiTask.close')} title={t('aiTask.close')}
            onClick={() => setNotice(null)}>×</button>
        </div>
      )}
      {askPush && !showNotice && (
        <div className="ai-task-notice ai-push-question" role="dialog" aria-label={t('push.title')}>
          <div className="ai-push-question-body">
            <strong>{t('push.ask')}</strong>
            <PushSetupPanel t={t} compact onChange={(state) => { if (state === 'on' || state === 'denied') closePushQuestion(); }} />
          </div>
          <button type="button" className="ai-task-notice-close" aria-label={t('push.notNow')} title={t('push.notNow')}
            onClick={closePushQuestion}>×</button>
        </div>
      )}
    </>
  );
}

import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';

const POLL_MS = 2000;
const MISSES_PREVIEW = 10;

// AI Model Settings: "Check search accuracy" on the live articles. The server
// asks a few questions about every article and checks the answer line reaches
// the AI (no AI call). Runs in the background; this card polls the progress.
export default function RetrievalAuditCard() {
  const { t } = useLanguage();
  const [audit, setAudit] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);
  const timerRef = useRef(null);

  const running = audit?.status === 'running';

  const load = async () => {
    try {
      const response = await api.get('/ai-settings/retrieval-audit');
      setAudit(response.data?.audit || null);
    } catch (loadError) {
      console.error('Load retrieval check error:', loadError);
    }
  };

  useEffect(() => {
    load();
    return () => clearTimeout(timerRef.current);
  }, []);

  useEffect(() => {
    clearTimeout(timerRef.current);
    if (running) timerRef.current = setTimeout(load, POLL_MS);
  }, [audit]);

  const handleStart = async () => {
    setError('');
    setStarting(true);
    setShowAll(false);
    try {
      const response = await api.post('/ai-settings/retrieval-audit', {});
      setAudit(response.data?.audit || { status: 'running', done: 0, total: 0 });
    } catch (startError) {
      if (startError.response?.status === 409) await load();
      else setError(t('ai.audit.failed'));
    } finally {
      setStarting(false);
    }
  };

  const result = audit?.result;
  const misses = result?.misses || [];
  const shownMisses = showAll ? misses : misses.slice(0, MISSES_PREVIEW);
  const percent = result?.rate == null ? '-' : `${(result.rate * 100).toFixed(1)}%`;
  const failed = audit?.status === 'failed';

  return (
    <section className="ais-settings-card ais-audit-card">
      <div className="ais-section-head">
        <div>
          <span className="ais-kicker">{t('ai.audit.kicker')}</span>
          <h2>{t('ai.audit.title')}</h2>
          <p className="ais-audit-hint">{t('ai.audit.hint')}</p>
        </div>

        <button
          type="button"
          className="ais-btn primary"
          onClick={handleStart}
          disabled={running || starting}
        >
          {running || starting ? t('ai.audit.checking') : t('ai.audit.start')}
        </button>
      </div>

      {running ? (
        <div className="ais-test-result success" role="status">
          <span className="ais-result-dot" />
          {audit.total
            ? t('ai.audit.progress', { done: audit.done, total: audit.total })
            : t('ai.audit.preparing')}
        </div>
      ) : null}

      {error || failed ? (
        <div className="ais-test-result error">
          <span className="ais-result-dot" />
          {error || t('ai.audit.failed')}
        </div>
      ) : null}

      {result ? (
        <>
          <div className="ais-audit-stats">
            <div className="ais-audit-score">
              <span>{t('ai.audit.score')}</span>
              <strong>{percent}</strong>
              <small>
                {t('ai.audit.summary', {
                  passed: result.passed,
                  total: result.total,
                  articles: result.articleCount,
                })}
              </small>
            </div>
            <div>
              <span>{t('ai.audit.wrongArticle')}</span>
              <strong>{result.wrongArticle}</strong>
            </div>
            <div>
              <span>{t('ai.audit.lineCut')}</span>
              <strong>{result.lineCut}</strong>
            </div>
          </div>

          <p className="ais-audit-meta">
            {t('ai.audit.lastRun', {
              time: new Date(result.finishedAt).toLocaleString(),
              seconds: Math.round(result.durationSeconds),
            })}
          </p>

          {misses.length ? (
            <>
              <h3 className="ais-audit-subtitle">{t('ai.audit.misses')}</h3>
              <p className="ais-audit-hint">{t('ai.audit.fixHint')}</p>
              <ol className="ais-audit-misses">
                {shownMisses.map((miss, index) => (
                  <li key={`${miss.article_id}-${index}`}>
                    <div className="ais-audit-miss-head">
                      <strong>“{miss.question}”</strong>
                      <span className={`ais-audit-cause ${miss.cause}`}>
                        {miss.cause === 'line_cut' ? t('ai.audit.lineCut') : t('ai.audit.wrongArticle')}
                      </span>
                    </div>
                    <div>
                      <span>{t('ai.audit.expected')}</span> {miss.article_title}
                    </div>
                    <div className="ais-audit-line">{miss.expected}</div>
                    {miss.cause === 'wrong_article' && miss.picked?.length ? (
                      <div>
                        <span>{t('ai.audit.picked')}</span> {miss.picked.join(' · ')}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ol>
              {misses.length > MISSES_PREVIEW ? (
                <button type="button" className="ais-btn secondary" onClick={() => setShowAll(!showAll)}>
                  {showAll ? t('ai.audit.showLess') : t('ai.audit.showAll', { count: misses.length })}
                </button>
              ) : null}
            </>
          ) : (
            <div className="ais-test-result success">
              <span className="ais-result-dot" />
              {t('ai.audit.noMisses')}
            </div>
          )}
        </>
      ) : !running && !failed && audit ? (
        <p className="ais-audit-meta">{t('ai.audit.never')}</p>
      ) : null}
    </section>
  );
}

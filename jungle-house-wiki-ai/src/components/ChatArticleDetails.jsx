import { useEffect, useRef, useState } from 'react';
import ArticleBody from './ArticleBody';
import api from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';

// "Show more details" under an AI Chat answer: the article the answer used,
// shown in place (no page change) with the same ArticleBody as the Knowledge
// Base article page, so text, images, links and attachments look identical.
export default function ChatArticleDetails({ articleId }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ status: 'idle', article: null, links: [] });
  // Load once, the first time it is opened; closing mid-load allows a retry.
  const requestedRef = useRef(false);

  useEffect(() => {
    if (!open || requestedRef.current) return undefined;
    requestedRef.current = true;
    const controller = new AbortController();
    let finished = false;

    const load = async () => {
      setState({ status: 'loading', article: null, links: [] });
      try {
        const response = await api.get(`/articles/${encodeURIComponent(articleId)}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        const article = response.data?.article_id ? response.data : null;

        // Related links are optional, exactly as on the article page.
        let links = [];
        try {
          const linksResponse = await api.get(`/article-links/${encodeURIComponent(articleId)}`, {
            signal: controller.signal,
          });
          links = Array.isArray(linksResponse.data) ? linksResponse.data : [];
        } catch {
          links = [];
        }
        if (controller.signal.aborted) return;
        finished = true;
        setState({ status: article ? 'ready' : 'error', article, links });
      } catch {
        if (!controller.signal.aborted) {
          finished = true;
          setState({ status: 'error', article: null, links: [] });
        }
      }
    };

    load();
    return () => {
      controller.abort();
      if (!finished) requestedRef.current = false;
    };
  }, [open, articleId]);

  return (
    <div className="chat-article-details" style={{ marginTop: '12px' }}>
      <button
        type="button"
        className="secondary-btn chat-article-details-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? `▲ ${t('chat.hideDetails')}` : `▼ ${t('chat.showMoreDetails')}`}
      </button>

      {open && state.status === 'loading' ? (
        <p style={{ marginTop: '10px', opacity: 0.75 }}>{t('chat.loadingArticle')}</p>
      ) : null}

      {open && state.status === 'error' ? (
        <p style={{ marginTop: '10px', opacity: 0.75 }}>{t('chat.articleUnavailable')}</p>
      ) : null}

      {open && state.status === 'ready' ? (
        // The article styles are scoped to .article-detail-page; only the
        // page's bottom space is removed so it sits neatly in the chat.
        <div className="article-detail-page" style={{ marginTop: '12px', paddingBottom: 0 }}>
          <ArticleBody key={state.article.article_id} article={state.article} links={state.links} />
        </div>
      ) : null}
    </div>
  );
}

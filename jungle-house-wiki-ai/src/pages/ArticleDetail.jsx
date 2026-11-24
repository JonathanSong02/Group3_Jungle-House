import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import ArticleBody from "../components/ArticleBody";
import api from "../services/api";
import "../styles/ArticleDetail.css";
import { useLanguage } from "../i18n/LanguageContext";

export default function ArticleDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [article, setArticle] = useState(null);
  const [links, setLinks] = useState([]);
  const [loadedArticleId, setLoadedArticleId] = useState(null);
  const loading = loadedArticleId !== id;

  useEffect(() => {
    const controller = new AbortController();

    const loadArticle = async () => {
      try {
        // The shared client uses /api on localhost (Vite proxy) and Vercel.
        // It also supplies Flask's session cookie automatically.
        const articleResponse = await api.get(`/articles/${encodeURIComponent(id)}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        const articleData = articleResponse.data;
        setArticle(articleData?.article_id ? articleData : null);

        // Related links are optional. A failure here must not erase an
        // article that was loaded successfully.
        try {
          const linksResponse = await api.get(`/article-links/${encodeURIComponent(id)}`, {
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          setLinks(Array.isArray(linksResponse.data) ? linksResponse.data : []);
        } catch (linksError) {
          if (controller.signal.aborted) return;
          console.warn("Related links could not be loaded:", linksError);
          setLinks([]);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error("Failed to load article detail:", err);
        setArticle(null);
        setLinks([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoadedArticleId(id);
        }
      }
    };

    loadArticle();
    return () => controller.abort();
  }, [id]);

  if (loading) {
    return (
      <div className="article-detail-page">
        <div className="article-detail-state" aria-live="polite">
          <span className="article-detail-state-spinner" aria-hidden="true" />
          <strong>{t("article.view.loadingTitle")}</strong>
          <p>{t("article.view.loadingText")}</p>
        </div>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="article-detail-page">
        <div className="article-detail-state article-detail-state-error" role="alert">
          <strong>{t("article.view.notFoundTitle")}</strong>
          <p>{t("article.view.notFoundText")}</p>
          <button type="button" className="secondary-btn" onClick={() => navigate(-1)}>
            {t("article.view.backToKb")}
          </button>
        </div>
      </div>
    );
  }


  return (
    <div className="article-detail-page">
      <button
        type="button"
        className="back-btn article-detail-back"
        onClick={() => navigate(-1)}
      >
        &larr; {t("article.view.backToKb")}
      </button>

      <PageHeader
        title={article.title}
        subtitle={
          article.sub_category
            ? `${article.category} > ${article.sub_category}`
            : t("article.view.category", { name: article.category })
        }
        actions={
          // Same rule as SourceBadge, checked here so PageHeader doesn't
          // render an empty actions box for every other article.
          article.source_type === "notion" && article.category !== "Notion" ? (
            <SourceBadge article={article} className="status-badge success" />
          ) : null
        }
      />

      {/* Content, attachments and related links: shared with AI Chat. */}
      <ArticleBody key={article.article_id} article={article} links={links} />
    </div>
  );
}
import { Link, useParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import { articles } from '../data/mockData';

export default function ArticleDetail() {
  const { id } = useParams();
  const article = articles.find((item) => String(item.id) === String(id));

  if (!article) {
    return (
      <div className="card-like">
        <h2>Article not found</h2>
        <Link className="text-link" to="/knowledge">
          Back to knowledge base
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={article.title}
        subtitle={`Category: ${article.category}`}
        actions={
          <Link className="secondary-btn link-btn" to="/knowledge">
            Back
          </Link>
        }
      />

      <article className="card-like">
        <p>{article.body}</p>
      </article>
    </div>
  );
}

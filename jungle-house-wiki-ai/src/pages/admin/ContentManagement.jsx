import { useState } from 'react';
import PageHeader from '../../components/PageHeader';
import { articles as initialArticles } from '../../data/mockData';

export default function ContentManagement() {
  const [articleList, setArticleList] = useState(initialArticles);
  const [newTitle, setNewTitle] = useState('');

  const addArticle = () => {
    if (!newTitle.trim()) return;
    setArticleList((prev) => [
      {
        id: Date.now(),
        title: newTitle.trim(),
        category: 'Training',
        summary: 'New article draft',
        body: 'Edit content here later.',
      },
      ...prev,
    ]);
    setNewTitle('');
  };

  return (
    <div>
      <PageHeader
        title="Content Management"
        subtitle="Create, edit, delete, and organize knowledge content."
      />

      <section className="card-like top-gap-sm">
        <div className="row-between wrap-gap">
          <input
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="New article title"
          />
          <button className="primary-btn narrow-btn" onClick={addArticle}>
            Add Article
          </button>
        </div>
      </section>

      <div className="stack-gap top-gap-sm">
        {articleList.map((article) => (
          <article key={article.id} className="card-like row-between wrap-gap">
            <div>
              <p className="eyebrow">{article.category}</p>
              <h3>{article.title}</h3>
              <p className="muted">{article.summary}</p>
            </div>
            <div className="button-group">
              <button className="secondary-btn">Edit</button>
              <button className="secondary-btn danger-btn">Delete</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

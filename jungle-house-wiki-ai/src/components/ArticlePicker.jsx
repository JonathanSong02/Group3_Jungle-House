import { useMemo, useState } from 'react';

// Pick Knowledge Base articles for a quiz (2026-11-26): search by title,
// category buttons, tick several, "select all listed", at most `max`.
// `selected` is a list of article ids as strings, in the order ticked.
export default function ArticlePicker({ articles, selected, onChange, max = 30, t, catLabel, idPrefix = 'article-picker' }) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [limitHit, setLimitHit] = useState(false);

  const categories = useMemo(
    () => [...new Set(articles.map((article) => article.category).filter(Boolean))],
    [articles]
  );
  const titleById = useMemo(
    () => new Map(articles.map((article) => [String(article.article_id), article.title])),
    [articles]
  );
  const listed = useMemo(() => {
    const words = search.trim().toLowerCase();
    return articles.filter((article) =>
      (category === 'All' || article.category === category) &&
      (!words || String(article.title || '').toLowerCase().includes(words)));
  }, [articles, search, category]);

  const chosen = new Set(selected);
  const listedIds = listed.map((article) => String(article.article_id));
  const allListedChosen = listedIds.length > 0 && listedIds.every((id) => chosen.has(id));
  const full = selected.length >= max;

  const update = (ids) => {
    setLimitHit(false);
    onChange(ids);
  };
  const toggle = (id) => {
    if (chosen.has(id)) update(selected.filter((item) => item !== id));
    else if (full) setLimitHit(true);
    else update([...selected, id]);
  };
  const toggleListed = () => {
    if (allListedChosen) {
      update(selected.filter((id) => !listedIds.includes(id)));
      return;
    }
    const room = max - selected.length;
    const adding = listedIds.filter((id) => !chosen.has(id));
    onChange([...selected, ...adding.slice(0, Math.max(0, room))]);
    setLimitHit(adding.length > room);
  };

  return (
    <div className="article-picker">
      <input
        type="search"
        className="article-picker-search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder={t('picker.search')}
        aria-label={t('picker.search')}
      />
      <div className="article-picker-categories" role="group" aria-label={t('picker.categories')}>
        {['All', ...categories].map((name) => (
          <button
            type="button"
            key={name}
            className={`article-picker-category ${category === name ? 'active' : ''}`}
            aria-pressed={category === name}
            onClick={() => setCategory(name)}
          >
            {name === 'All' ? t('picker.all') : catLabel(name)}
          </button>
        ))}
      </div>

      <div className="article-picker-list" role="group" aria-label={t('picker.listLabel')}>
        {listed.length > 0 && (
          <label className="article-picker-all">
            <input type="checkbox" checked={allListedChosen} onChange={toggleListed} />
            <span>{t('picker.selectListed', { n: listed.length })}</span>
          </label>
        )}
        {listed.map((article) => {
          const id = String(article.article_id);
          const isChosen = chosen.has(id);
          return (
            <label key={id} className={`article-picker-row ${isChosen ? 'chosen' : ''}`} htmlFor={`${idPrefix}-${id}`}>
              <input
                id={`${idPrefix}-${id}`}
                type="checkbox"
                checked={isChosen}
                disabled={!isChosen && full}
                onChange={() => toggle(id)}
              />
              <span>
                {article.title}
                {article.category ? ` — ${catLabel(article.category)}` : ''}
              </span>
            </label>
          );
        })}
        {listed.length === 0 && <p className="article-picker-empty">{t('picker.none')}</p>}
      </div>

      <div className="article-picker-footer">
        <span className="article-picker-count">{t('picker.selected', { n: selected.length, max })}</span>
        {selected.length > 0 && (
          <button type="button" className="article-picker-clear" onClick={() => update([])}>{t('picker.clear')}</button>
        )}
      </div>
      {limitHit && (
        <p className="article-picker-limit" role="status">{t('picker.max', { max })}</p>
      )}
      {selected.length > 0 && (
        <div className="article-picker-chips">
          {selected.map((id) => (
            <span key={id} className="article-picker-chip">
              {titleById.get(id) || `#${id}`}
              <button type="button" aria-label={t('picker.remove', { title: titleById.get(id) || `#${id}` })}
                onClick={() => update(selected.filter((item) => item !== id))}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

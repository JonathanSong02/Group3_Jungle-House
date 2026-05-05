import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';

export default function Analytics() {
  const [activeTab, setActiveTab] = useState('questions');

  const [summary, setSummary] = useState({
    total_questions: 0,
    unique_questions: 0,
    knowledge_gap_count: 0,
    fallback_count: 0,
    escalation_count: 0,
  });

  const [topQuestions, setTopQuestions] = useState([]);
  const [knowledgeGaps, setKnowledgeGaps] = useState([]);
  const [searchLogs, setSearchLogs] = useState([]);

  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setError('');

      const response = await api.get('/analytics');

      setSummary(response.data.summary || {});
      setTopQuestions(response.data.top_questions || []);
      setKnowledgeGaps(response.data.knowledge_gaps || []);
      setSearchLogs(response.data.search_logs || []);
    } catch (err) {
      console.error('ANALYTICS ERROR:', err);
      setError(err.response?.data?.message || 'Unable to load analytics data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const filteredTopQuestions = useMemo(() => {
    return topQuestions.filter((item) => {
      const search = searchText.toLowerCase();

      return (
        String(item.question || '').toLowerCase().includes(search) ||
        String(item.category || '').toLowerCase().includes(search)
      );
    });
  }, [topQuestions, searchText]);

  const filteredKnowledgeGaps = useMemo(() => {
    return knowledgeGaps.filter((item) => {
      const search = searchText.toLowerCase();

      return (
        String(item.question || '').toLowerCase().includes(search) ||
        String(item.category || '').toLowerCase().includes(search) ||
        String(item.source || '').toLowerCase().includes(search)
      );
    });
  }, [knowledgeGaps, searchText]);

  const filteredSearchLogs = useMemo(() => {
    return searchLogs.filter((item) => {
      const search = searchText.toLowerCase();

      return (
        String(item.question || '').toLowerCase().includes(search) ||
        String(item.category || '').toLowerCase().includes(search) ||
        String(item.source || '').toLowerCase().includes(search)
      );
    });
  }, [searchLogs, searchText]);

  const formatConfidence = (value) => {
    const number = Number(value || 0);
    return `${Math.round(number * 100)}%`;
  };

  const renderSummaryCards = () => {
    return (
      <div className="three-column-grid" style={{ marginBottom: '1.5rem' }}>
        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Total Questions
          </p>
          <h2 style={{ margin: 0 }}>{summary.total_questions || 0}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Unique Questions
          </p>
          <h2 style={{ margin: 0 }}>{summary.unique_questions || 0}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Knowledge Gaps
          </p>
          <h2 style={{ margin: 0 }}>{summary.knowledge_gap_count || 0}</h2>
        </section>
      </div>
    );
  };

  const renderToolbar = () => {
    return (
      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: '1rem',
            alignItems: 'end',
          }}
        >
          <div>
            <label className="form-label">Search Analytics</label>
            <input
              type="text"
              placeholder="Search question, category, or source..."
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </div>

          <button
            type="button"
            className="secondary-btn"
            onClick={fetchAnalytics}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </section>
    );
  };

  const renderQuestionAnalytics = () => {
    return (
      <section className="card-like table-card">
        <h3>Question Analytics</h3>
        <p className="muted">
          This section analyses what users ask most frequently in the AI chat.
        </p>

        {filteredTopQuestions.length === 0 ? (
          <p className="muted">No question analytics found yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Category</th>
                <th>Asked Count</th>
                <th>Last Asked</th>
              </tr>
            </thead>

            <tbody>
              {filteredTopQuestions.map((item, index) => (
                <tr key={`${item.question}-${index}`}>
                  <td>{item.question}</td>
                  <td>{item.category || '-'}</td>
                  <td>{item.count}</td>
                  <td>{item.last_asked || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    );
  };

  const renderKnowledgeGap = () => {
    return (
      <section className="card-like table-card">
        <h3>Knowledge Gap</h3>
        <p className="muted">
          This section identifies low-confidence, fallback, or escalation-needed questions.
        </p>

        {filteredKnowledgeGaps.length === 0 ? (
          <p className="muted">No knowledge gaps found yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Category</th>
                <th>Confidence</th>
                <th>Source</th>
                <th>Reason</th>
                <th>Time</th>
              </tr>
            </thead>

            <tbody>
              {filteredKnowledgeGaps.map((item, index) => (
                <tr key={`${item.question}-${index}`}>
                  <td>{item.question}</td>
                  <td>{item.category || '-'}</td>
                  <td>{formatConfidence(item.confidence)}</td>
                  <td>{item.source || '-'}</td>
                  <td>{item.reason || '-'}</td>
                  <td>{item.time || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    );
  };

  const renderSearchLog = () => {
    return (
      <section className="card-like table-card">
        <h3>Search Log</h3>
        <p className="muted">
          This section tracks recent user search behaviour and AI chat interaction patterns.
        </p>

        {filteredSearchLogs.length === 0 ? (
          <p className="muted">No search logs found yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Category</th>
                <th>Confidence</th>
                <th>Source</th>
                <th>Fallback</th>
                <th>Escalation</th>
                <th>Time</th>
              </tr>
            </thead>

            <tbody>
              {filteredSearchLogs.map((item, index) => (
                <tr key={`${item.question}-${index}`}>
                  <td>{item.question}</td>
                  <td>{item.category || '-'}</td>
                  <td>{formatConfidence(item.confidence)}</td>
                  <td>{item.source || '-'}</td>
                  <td>{item.fallback ? 'Yes' : 'No'}</td>
                  <td>{item.escalation_ready ? 'Yes' : 'No'}</td>
                  <td>{item.timestamp || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    );
  };

  const renderContent = () => {
    if (loading && topQuestions.length === 0 && knowledgeGaps.length === 0 && searchLogs.length === 0) {
      return (
        <section className="card-like">
          <p className="muted">Loading analytics data...</p>
        </section>
      );
    }

    if (activeTab === 'questions') {
      return renderQuestionAnalytics();
    }

    if (activeTab === 'gaps') {
      return renderKnowledgeGap();
    }

    if (activeTab === 'search') {
      return renderSearchLog();
    }

    return null;
  };

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Track popular questions, search trends, and knowledge gaps."
      />

      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <h3>Analytics Overview</h3>
        <p className="muted">
          The Analytics module helps management understand system performance,
          staff learning behaviour, and missing knowledge areas. It supports
          evidence-based updates to training materials and helps improve the
          system over time based on real usage.
        </p>
      </section>

      {renderSummaryCards()}

      {error ? <p className="error-text">{error}</p> : null}

      <div
        className="tab-row"
        style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          className={activeTab === 'questions' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('questions')}
        >
          Question Analytics
        </button>

        <button
          type="button"
          className={activeTab === 'gaps' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('gaps')}
        >
          Knowledge Gap
        </button>

        <button
          type="button"
          className={activeTab === 'search' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('search')}
        >
          Search Log
        </button>
      </div>

      {renderToolbar()}

      {renderContent()}
    </div>
  );
}
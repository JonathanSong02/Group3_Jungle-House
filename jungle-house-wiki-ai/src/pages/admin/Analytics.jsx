import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import './styles/Analytics.css';

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

  const activeRows =
    activeTab === 'questions'
      ? filteredTopQuestions
      : activeTab === 'gaps'
      ? filteredKnowledgeGaps
      : filteredSearchLogs;

  return (
    <div className="an-page">
      <PageHeader
        title="Analytics"
        subtitle="Track usage and knowledge gaps."
      />

      <section className="an-summary-grid">
        <div className="an-summary-card questions">
          <span>Total Questions</span>
          <strong>{summary.total_questions || 0}</strong>
        </div>

        <div className="an-summary-card unique">
          <span>Unique</span>
          <strong>{summary.unique_questions || 0}</strong>
        </div>

        <div className="an-summary-card gaps">
          <span>Knowledge Gaps</span>
          <strong>{summary.knowledge_gap_count || 0}</strong>
        </div>

        <div className="an-summary-card fallback">
          <span>Fallback</span>
          <strong>{summary.fallback_count || 0}</strong>
        </div>

        <div className="an-summary-card escalation">
          <span>Escalations</span>
          <strong>{summary.escalation_count || 0}</strong>
        </div>
      </section>

      {error ? <div className="an-feedback">{error}</div> : null}

      <section className="an-workspace">
        <div className="an-workspace-head">
          <div className="an-tabs">
            <button
              type="button"
              className={activeTab === 'questions' ? 'active' : ''}
              onClick={() => setActiveTab('questions')}
            >
              Questions
              <span>{topQuestions.length}</span>
            </button>

            <button
              type="button"
              className={activeTab === 'gaps' ? 'active' : ''}
              onClick={() => setActiveTab('gaps')}
            >
              Knowledge Gaps
              <span>{knowledgeGaps.length}</span>
            </button>

            <button
              type="button"
              className={activeTab === 'search' ? 'active' : ''}
              onClick={() => setActiveTab('search')}
            >
              Search Log
              <span>{searchLogs.length}</span>
            </button>
          </div>

          <div className="an-tools">
            <input
              type="search"
              placeholder="Search analytics"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />

            <button
              type="button"
              className="an-btn"
              onClick={fetchAnalytics}
              disabled={loading}
            >
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        {loading && topQuestions.length === 0 && knowledgeGaps.length === 0 && searchLogs.length === 0 ? (
          <div className="an-empty">
            <strong>Loading analytics...</strong>
          </div>
        ) : activeRows.length === 0 ? (
          <div className="an-empty">
            <strong>No analytics found</strong>
          </div>
        ) : activeTab === 'questions' ? (
          <div className="an-table-wrap">
            <table className="an-table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Category</th>
                  <th>Asked</th>
                  <th>Last Asked</th>
                </tr>
              </thead>

              <tbody>
                {filteredTopQuestions.map((item, index) => (
                  <tr key={`${item.question}-${index}`}>
                    <td><strong>{item.question}</strong></td>
                    <td><span className="an-chip blue">{item.category || '-'}</span></td>
                    <td><span className="an-count">{item.count}</span></td>
                    <td>{item.last_asked || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : activeTab === 'gaps' ? (
          <div className="an-table-wrap">
            <table className="an-table">
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
                    <td><strong>{item.question}</strong></td>
                    <td><span className="an-chip amber">{item.category || '-'}</span></td>
                    <td>
                      <span className="an-confidence">
                        <i style={{ width: formatConfidence(item.confidence) }} />
                        <strong>{formatConfidence(item.confidence)}</strong>
                      </span>
                    </td>
                    <td>{item.source || '-'}</td>
                    <td>{item.reason || '-'}</td>
                    <td>{item.time || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="an-table-wrap">
            <table className="an-table">
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
                    <td><strong>{item.question}</strong></td>
                    <td><span className="an-chip violet">{item.category || '-'}</span></td>
                    <td>{formatConfidence(item.confidence)}</td>
                    <td>{item.source || '-'}</td>
                    <td>
                      <span className={`an-boolean ${item.fallback ? 'yes' : 'no'}`}>
                        {item.fallback ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td>
                      <span className={`an-boolean ${item.escalation_ready ? 'yes' : 'no'}`}>
                        {item.escalation_ready ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td>{item.timestamp || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

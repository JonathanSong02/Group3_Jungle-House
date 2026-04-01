import PageHeader from '../../components/PageHeader';
import { analyticsData } from '../../data/mockData';

export default function Analytics() {
  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Track popular questions, search trends, and knowledge gaps."
      />

      <div className="three-column-grid">
        <section className="card-like">
          <h3>Top Questions</h3>
          <ul className="simple-list">
            {analyticsData.topQuestions.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>

        <section className="card-like">
          <h3>Knowledge Gaps</h3>
          <ul className="simple-list">
            {analyticsData.knowledgeGaps.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>

        <section className="card-like">
          <h3>Search Terms</h3>
          <ul className="simple-list">
            {analyticsData.searchTerms.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      </div>
    </div>
  );
}

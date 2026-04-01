import { useState } from 'react';
import PageHeader from '../../components/PageHeader';

export default function AISettings() {
  const [settings, setSettings] = useState({
    confidenceThreshold: 0.75,
    autoEscalation: true,
    modelName: 'Small pretrained model',
  });

  return (
    <div>
      <PageHeader
        title="AI Settings"
        subtitle="Manage confidence threshold and AI control settings from the frontend panel."
      />

      <section className="card-like form-stack">
        <label>
          Confidence Threshold
          <input
            type="number"
            step="0.01"
            value={settings.confidenceThreshold}
            onChange={(event) =>
              setSettings((prev) => ({ ...prev, confidenceThreshold: event.target.value }))
            }
          />
        </label>

        <label>
          Model Name
          <input
            value={settings.modelName}
            onChange={(event) =>
              setSettings((prev) => ({ ...prev, modelName: event.target.value }))
            }
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={settings.autoEscalation}
            onChange={(event) =>
              setSettings((prev) => ({ ...prev, autoEscalation: event.target.checked }))
            }
          />
          Enable auto-escalation for weak answers
        </label>

        <button className="primary-btn">Save Settings</button>
      </section>
    </div>
  );
}

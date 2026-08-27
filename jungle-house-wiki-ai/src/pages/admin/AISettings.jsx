import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const PROVIDER_OPTIONS = [
  {
    value: 'gemini',
    label: 'Gemini',
    // gemini-flash-latest is Google's own recommended alias -- it always
    // points at the current best flash model, avoiding the version-number
    // guessing game (older pinned versions get retired over time).
    models: ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-2.5-flash-lite'],
  },
  {
    value: 'openai',
    label: 'OpenAI / GPT',
    models: ['gpt-4o-mini', 'gpt-4.1-mini'],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    models: ['deepseek-chat'],
  },
  {
    value: 'anthropic',
    label: 'Claude / Anthropic',
    models: ['claude-3-5-haiku-latest', 'claude-3-5-sonnet-latest'],
  },
];

const getModelSuggestions = (providerValue) =>
  PROVIDER_OPTIONS.find((option) => option.value === providerValue)?.models || [];

export default function AISettings() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;

  const [form, setForm] = useState({
    provider: 'gemini',
    model_name: 'gemini-flash-latest',
    api_key: '',
  });

  const [currentConfig, setCurrentConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState('');
  const [testResult, setTestResult] = useState(null);

  const fetchSettings = async () => {
    try {
      setLoading(true);

      const response = await api.get('/ai-settings');
      const config = response.data?.config || null;

      setCurrentConfig(config);

      if (config) {
        setForm((prev) => ({
          ...prev,
          provider: config.provider || prev.provider,
          model_name: config.modelName || prev.model_name,
        }));
      }
    } catch (error) {
      console.error('Fetch AI settings error:', error);
      setMessage('Failed to load AI settings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleProviderChange = (event) => {
    const provider = event.target.value;
    const suggestions = getModelSuggestions(provider);

    setForm((prev) => ({
      ...prev,
      provider,
      model_name: suggestions[0] || '',
    }));

    setTestResult(null);
  };

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));

    setTestResult(null);
  };

  const handleTestConnection = async () => {
    if (!form.model_name.trim()) {
      setMessage('Please enter a model name before testing.');
      return;
    }

    if (!form.api_key.trim() && !currentConfig) {
      setMessage('Please paste an API key before testing.');
      return;
    }

    try {
      setTesting(true);
      setMessage('');
      setTestResult(null);

      const response = await api.post('/ai-settings/test', {
        user_id: actorId,
        provider: form.provider,
        model_name: form.model_name.trim(),
        api_key: form.api_key.trim(),
      });

      setTestResult({
        success: Boolean(response.data?.success),
        message: response.data?.message || 'Test completed.',
      });

      // Testing the already-saved config (no new key typed) updates its
      // test_status in the database, but this page's "Current Active AI
      // Provider" card was only loaded once on page open -- refetch so it
      // reflects the result instead of permanently showing "Not tested".
      if (!form.api_key.trim()) {
        fetchSettings();
      }
    } catch (error) {
      console.error('Test AI connection error:', error);
      setTestResult({
        success: false,
        message:
          error.response?.data?.message ||
          'AI provider connection failed. Please check your API key.',
      });

      if (!form.api_key.trim()) {
        fetchSettings();
      }
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (event) => {
    event.preventDefault();

    if (!form.model_name.trim()) {
      setMessage('Model name is required.');
      return;
    }

    if (!form.api_key.trim()) {
      setMessage('API key is required.');
      return;
    }

    try {
      setSaving(true);
      setMessage('');

      const response = await api.post('/ai-settings', {
        updated_by: actorId,
        provider: form.provider,
        model_name: form.model_name.trim(),
        api_key: form.api_key.trim(),
      });

      setMessage(response.data?.message || 'AI settings saved successfully.');
      setCurrentConfig(response.data?.config || null);
      setTestResult(null);

      // Never keep the raw key sitting in state longer than needed.
      setForm((prev) => ({ ...prev, api_key: '' }));
    } catch (error) {
      console.error('Save AI settings error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to save AI settings.'
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="AI Model Settings"
        subtitle="Choose which AI provider powers AI features, and connect it with an API key."
      />

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      <section className="card-like top-gap-sm">
        <h3>Current Active AI Provider</h3>

        {loading ? (
          <p className="muted top-gap-sm">Loading...</p>
        ) : currentConfig ? (
          <div className="cards-grid top-gap-sm">
            <p className="muted">
              Provider: <strong>{currentConfig.providerLabel}</strong>
            </p>
            <p className="muted">
              Model: <strong>{currentConfig.modelName}</strong>
            </p>
            <p className="muted">
              API Key: <strong>{currentConfig.keyHint || '-'}</strong>
            </p>
            <p className="muted">
              Status:{' '}
              <strong>
                {currentConfig.testStatus === 'connected'
                  ? 'Connected'
                  : currentConfig.testStatus === 'failed'
                  ? 'Failed'
                  : 'Not tested'}
              </strong>
            </p>
            <p className="muted">
              Last Tested: <strong>{currentConfig.lastTestedAt || '-'}</strong>
            </p>
          </div>
        ) : (
          <p className="muted top-gap-sm">
            No AI provider configured yet. AI features that need real AI
            generation will show a friendly "not configured" message until
            this is set up.
          </p>
        )}
      </section>

      <section className="card-like top-gap">
        <h3>Update AI Provider</h3>
        <p className="muted">
          Paste the API key once — it is encrypted and stored securely, and
          is never shown again after saving.
        </p>

        <form className="form-grid top-gap" onSubmit={handleSave}>
          <label>
            Choose AI Provider
            <select
              name="provider"
              value={form.provider}
              onChange={handleProviderChange}
            >
              {PROVIDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Model Name
            <input
              list="ai-model-suggestions"
              name="model_name"
              value={form.model_name}
              onChange={handleChange}
              placeholder="Example: gemini-1.5-flash"
            />
            <datalist id="ai-model-suggestions">
              {getModelSuggestions(form.provider).map((modelName) => (
                <option key={modelName} value={modelName} />
              ))}
            </datalist>
          </label>

          <label className="full-width">
            API Key
            <input
              type="password"
              name="api_key"
              value={form.api_key}
              onChange={handleChange}
              placeholder={
                currentConfig
                  ? 'Enter a new key to replace the saved one'
                  : 'Paste API key here'
              }
              autoComplete="off"
            />
          </label>

          {testResult && (
            <p
              className={`full-width ${testResult.success ? 'success-text' : 'error-text'}`}
            >
              {testResult.message}
            </p>
          )}

          <div className="full-width button-group wrap-gap">
            <button
              type="button"
              className="secondary-btn"
              onClick={handleTestConnection}
              disabled={testing}
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>

            <button className="primary-btn" type="submit" disabled={saving}>
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

import { useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateServerMessage } from '../../i18n/serverMessages';
import './styles/AISettings.css';

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

const getProviderLabel = (providerValue, fallback = 'AI Provider') =>
  PROVIDER_OPTIONS.find((option) => option.value === providerValue)?.label ||
  providerValue ||
  fallback;

// "⭐ gemini-3.8-flash · Recommended · Stable" -- labels help pick a model
// that can chat and will not be shut down.
const modelOptionLabel = (model, currentConfig, provider, t) => {
  const tags = [];
  // "Recommended" already means a stable chat model, so it replaces "Stable".
  if (model.recommended) tags.push(t('ai.tag.recommended'));
  else if (model.chat && !model.preview) tags.push(t('ai.tag.stable'));
  if (model.preview) tags.push(t('ai.tag.preview'));
  if (!model.chat) tags.push(t('ai.tag.notChat'));
  if (currentConfig?.provider === provider && currentConfig?.modelName === model.id) {
    tags.push(t('ai.tag.current'));
  }
  return `${model.recommended ? '⭐ ' : ''}${model.id}${tags.length ? ` · ${tags.join(' · ')}` : ''}`;
};

export default function AISettings() {
  const { user } = useAuth();
  const { t } = useLanguage();
  const providerLabel = (value) => getProviderLabel(value, t('ai.providerDefault'));
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
  // Live model list from the provider (labelled), manual typing as fallback.
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [manualModel, setManualModel] = useState(false);
  // The saved key is shown masked; Edit opens an empty box for a new one.
  const [editingKey, setEditingKey] = useState(false);
  // Save is allowed only after a successful test of exactly what is on screen.
  const [testedSignature, setTestedSignature] = useState('');

  const usingSavedKey =
    Boolean(currentConfig) && currentConfig.provider === form.provider && !editingKey;
  const formSignature = `${form.provider}|${form.model_name.trim()}|${
    usingSavedKey ? 'saved-key' : form.api_key.trim()
  }`;
  const canSave = Boolean(testedSignature) && testedSignature === formSignature;

  const fetchModels = async (provider, apiKey = '') => {
    try {
      setModelsLoading(true);
      const response = await api.post(
        '/ai-settings/models',
        { provider, api_key: apiKey },
        { timeout: 30000 }
      );
      setModels(Array.isArray(response.data?.models) ? response.data.models : []);
    } catch (error) {
      console.error('Load AI models error:', error);
      setModels([]);
      setManualModel(true);
      setMessage(
        translateServerMessage(t, error.response?.data?.message) || t('ai.err.models')
      );
    } finally {
      setModelsLoading(false);
    }
  };

  const fetchSettings = async (applyToForm = true) => {
    try {
      setLoading(true);

      const response = await api.get('/ai-settings');
      const config = response.data?.config || null;

      setCurrentConfig(config);

      if (config && applyToForm) {
        setForm((prev) => ({
          ...prev,
          provider: config.provider || prev.provider,
          model_name: config.modelName || prev.model_name,
        }));
        fetchModels(config.provider || 'gemini');
      }
    } catch (error) {
      console.error('Fetch AI settings error:', error);
      setMessage(t('ai.err.load'));
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
    const backToSaved = Boolean(currentConfig) && currentConfig.provider === provider;

    setForm((prev) => ({
      ...prev,
      provider,
      api_key: '',
      model_name: backToSaved ? currentConfig.modelName : suggestions[0] || '',
    }));

    setTestResult(null);
    setModels([]);
    setManualModel(!backToSaved);
    // Another provider always needs its own key.
    setEditingKey(!backToSaved);

    if (backToSaved) {
      fetchModels(provider);
    }
  };

  const handleModelSelect = (event) => {
    const { value } = event.target;

    if (value === '__manual__') {
      setManualModel(true);
      return;
    }

    setForm((prev) => ({ ...prev, model_name: value }));
    setTestResult(null);
  };

  const handleRefreshModels = () => {
    if (!usingSavedKey && !form.api_key.trim()) {
      setMessage(t('ai.err.keyForProvider'));
      return;
    }

    setMessage('');
    setManualModel(false);
    fetchModels(form.provider, usingSavedKey ? '' : form.api_key.trim());
  };

  const handleEditKey = () => {
    setEditingKey(true);
    setForm((prev) => ({ ...prev, api_key: '' }));
    setTestResult(null);
  };

  const handleCancelKeyEdit = () => {
    setEditingKey(false);
    setForm((prev) => ({ ...prev, api_key: '' }));
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
      setMessage(t('ai.err.modelBeforeTest'));
      return;
    }

    if (!usingSavedKey && !form.api_key.trim()) {
      setMessage(t('ai.err.keyBeforeTest'));
      return;
    }

    const signatureAtTest = formSignature;
    const testsSavedModel =
      usingSavedKey && form.model_name.trim() === (currentConfig?.modelName || '');

    try {
      setTesting(true);
      setMessage('');
      setTestResult(null);
      setTestedSignature('');

      // The backend's own wait for the AI provider can take up to ~90s
      // (a slow/hanging provider, not just a fast reject), so this call
      // needs a longer timeout than the shared API client's 10s default.
      const response = await api.post(
        '/ai-settings/test',
        {
          user_id: actorId,
          provider: form.provider,
          model_name: form.model_name.trim(),
          api_key: usingSavedKey ? '' : form.api_key.trim(),
        },
        { timeout: 150000 }
      );

      const success = Boolean(response.data?.success);
      setTestResult({
        success,
        message: translateServerMessage(t, response.data?.message) || t('ai.testDone'),
      });

      if (success) {
        setTestedSignature(signatureAtTest);
      }

      // Refresh the "last tested" card only when the saved model was tested,
      // without resetting what is chosen in the form.
      if (testsSavedModel) {
        fetchSettings(false);
      }
    } catch (error) {
      console.error('Test AI connection error:', error);
      setTestResult({
        success: false,
        message:
          translateServerMessage(t, error.response?.data?.message) ||
          t('ai.err.connection'),
      });

      if (testsSavedModel) {
        fetchSettings(false);
      }
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (event) => {
    event.preventDefault();

    if (!form.model_name.trim()) {
      setMessage(t('ai.err.modelRequired'));
      return;
    }

    if (!usingSavedKey && !form.api_key.trim()) {
      setMessage(t('ai.err.keyRequired'));
      return;
    }

    if (!canSave) {
      setMessage(t('ai.testFirst'));
      return;
    }

    try {
      setSaving(true);
      setMessage('');

      const response = await api.post('/ai-settings', {
        updated_by: actorId,
        provider: form.provider,
        model_name: form.model_name.trim(),
        api_key: usingSavedKey ? '' : form.api_key.trim(),
      });

      setMessage(t('ai.ok.saved'));
      setCurrentConfig(response.data?.config || null);
      setTestResult(null);
      setTestedSignature('');
      setEditingKey(false);

      // Never keep the raw key sitting in state longer than needed.
      setForm((prev) => ({ ...prev, api_key: '' }));
    } catch (error) {
      console.error('Save AI settings error:', error);
      setMessage(
        translateServerMessage(t, error.response?.data?.message) || t('ai.err.save')
      );
    } finally {
      setSaving(false);
    }
  };

  const currentStatus =
    currentConfig?.testStatus === 'connected'
      ? t('ai.status.connected')
      : currentConfig?.testStatus === 'failed'
      ? t('ai.status.failed')
      : t('ai.status.untested');

  const currentStatusClass =
    currentConfig?.testStatus === 'connected'
      ? 'connected'
      : currentConfig?.testStatus === 'failed'
      ? 'failed'
      : 'untested';

  return (
    <div className="ais-page">
      <PageHeader
        title={t('ai.title')}
        subtitle={t('ai.subtitle')}
      />

      {message ? <div className="ais-feedback">{message}</div> : null}

      <div className="ais-layout">
        <section className="ais-status-card">
          <div className="ais-status-top">
            <div className="ais-orb">
              <span>AI</span>
            </div>

            <div>
              <span className="ais-kicker">{t('ai.currentModel')}</span>
              <h2>
                {loading
                  ? t('ai.loading')
                  : currentConfig
                  ? currentConfig.providerLabel ||
                    providerLabel(currentConfig.provider)
                  : t('ai.notConfigured')}
              </h2>
            </div>

            {!loading && currentConfig ? (
              <span className={`ais-status-pill ${currentStatusClass}`}>
                <i />
                {currentStatus}
              </span>
            ) : null}
          </div>

          {loading ? (
            <div className="ais-loading-block">
              <span />
              <span />
              <span />
            </div>
          ) : currentConfig ? (
            <>
              <div className="ais-model-name">
                <span>{t('ai.model')}</span>
                <strong>{currentConfig.modelName}</strong>
              </div>

              <div className="ais-config-grid">
                <div>
                  <span>{t('ai.apiKey')}</span>
                  <strong>{currentConfig.keyHint || '-'}</strong>
                </div>

                <div>
                  <span>{t('ai.lastTested')}</span>
                  <strong>{currentConfig.lastTestedAt || '-'}</strong>
                </div>
              </div>
            </>
          ) : (
            <div className="ais-empty-config">
              <strong>{t('ai.noProvider')}</strong>
              <span>{t('ai.noProviderHint')}</span>
            </div>
          )}

          <div className="ais-ai-note">
            <span className="ais-ai-note-icon">✦</span>
            <div>
              <strong>{t('ai.engine')}</strong>
              <span>{t('ai.engineHint')}</span>
            </div>
          </div>
        </section>

        <section className="ais-settings-card">
          <div className="ais-section-head">
            <div>
              <span className="ais-kicker">{t('ai.configuration')}</span>
              <h2>{t('ai.providerSettings')}</h2>
            </div>

            <span className="ais-provider-chip">
              {providerLabel(form.provider)}
            </span>
          </div>

          <form className="ais-form" onSubmit={handleSave}>
            <div className="ais-form-grid">
              <label className="ais-field">
                <span>{t('ai.provider')}</span>
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

              <div className="ais-field">
                <span>{t('ai.model')}</span>
                <div className="ais-inline-row">
                  {!manualModel && models.length > 0 ? (
                    <select
                      name="model_name"
                      aria-label={t('ai.model')}
                      value={form.model_name}
                      onChange={handleModelSelect}
                    >
                      {form.model_name && !models.some((model) => model.id === form.model_name) ? (
                        <option value={form.model_name}>
                          {form.model_name} · {t('ai.tag.current')}
                        </option>
                      ) : null}
                      {models.map((model) => (
                        <option key={model.id} value={model.id}>
                          {modelOptionLabel(model, currentConfig, form.provider, t)}
                        </option>
                      ))}
                      <option value="__manual__">{t('ai.manualModel')}</option>
                    </select>
                  ) : (
                    <input
                      list="ai-model-suggestions"
                      name="model_name"
                      aria-label={t('ai.model')}
                      value={form.model_name}
                      onChange={handleChange}
                      placeholder={modelsLoading ? t('ai.loadingModels') : t('ai.modelName')}
                    />
                  )}

                  <button
                    type="button"
                    className="ais-btn secondary"
                    onClick={handleRefreshModels}
                    disabled={modelsLoading}
                    title={t('ai.refreshModels')}
                    aria-label={t('ai.refreshModels')}
                  >
                    {modelsLoading ? '…' : '⟳'}
                  </button>
                </div>

                <datalist id="ai-model-suggestions">
                  {getModelSuggestions(form.provider).map((modelName) => (
                    <option key={modelName} value={modelName} />
                  ))}
                </datalist>
              </div>
            </div>

            <div className="ais-field ais-field-full">
              <span>{t('ai.apiKey')}</span>
              <div className="ais-inline-row">
                <div className="ais-key-input">
                  {usingSavedKey ? (
                    <input
                      type="text"
                      name="api_key"
                      aria-label={t('ai.apiKey')}
                      value={currentConfig.keyHint || '********'}
                      disabled
                      readOnly
                    />
                  ) : (
                    <input
                      type="password"
                      name="api_key"
                      aria-label={t('ai.apiKey')}
                      value={form.api_key}
                      onChange={handleChange}
                      placeholder={
                        currentConfig
                          ? t('ai.replaceKey')
                          : t('ai.pasteKey')
                      }
                      autoComplete="off"
                    />
                  )}
                  <span>{t('ai.encrypted')}</span>
                </div>

                {usingSavedKey ? (
                  <button type="button" className="ais-btn secondary" onClick={handleEditKey}>
                    {t('ai.edit')}
                  </button>
                ) : currentConfig && currentConfig.provider === form.provider ? (
                  <button type="button" className="ais-btn secondary" onClick={handleCancelKeyEdit}>
                    {t('ai.cancel')}
                  </button>
                ) : null}
              </div>
            </div>

            {testResult ? (
              <div
                className={`ais-test-result ${
                  testResult.success ? 'success' : 'error'
                }`}
              >
                <span className="ais-result-dot" />
                {testResult.message}
              </div>
            ) : null}

            <div className="ais-actions">
              <button
                type="button"
                className="ais-btn secondary"
                onClick={handleTestConnection}
                disabled={testing}
              >
                {testing ? t('ai.testing') : t('ai.test')}
              </button>

              <button
                className="ais-btn primary"
                type="submit"
                disabled={saving || !canSave}
                title={canSave ? undefined : t('ai.testFirst')}
              >
                {saving ? t('ai.saving') : t('ai.save')}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}

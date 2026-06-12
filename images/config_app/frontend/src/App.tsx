import { useState, useEffect, useCallback } from 'react';
import { Save, CheckCircle, AlertCircle, Eye, EyeOff, Zap, Plug, Loader2 } from 'lucide-react';

interface Variable {
  key: string;
  label: string;
  group: string;
  type: string;
  required?: boolean;
  default?: string;
  placeholder?: string;
  description?: string;
  options?: string[];
}

interface Group {
  id: string;
  title: string;
  description: string;
}

interface Schema {
  groups: Group[];
  variables: Variable[];
  presets: Record<string, Record<string, string>>;
}

export function App() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [originalValues, setOriginalValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});
  const [validation, setValidation] = useState<{ valid: boolean; missing: string[] } | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    reply?: string;
    model?: string;
    latency_s?: number;
    error?: string;
  } | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [schemaRes, envRes, validRes] = await Promise.all([
        fetch('/api/schema'),
        fetch('/api/env'),
        fetch('/api/validate'),
      ]);
      const schemaData = await schemaRes.json();
      const envData = await envRes.json();
      const validData = await validRes.json();

      setSchema(schemaData);
      setValues(envData.values);
      setOriginalValues(envData.values);
      setValidation(validData);
    } catch (e) {
      console.error('Failed to load config', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleChange = (key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setSaveStatus('idle');
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus('idle');
    try {
      // Only send values that changed
      const updates: Record<string, string> = {};
      for (const [key, val] of Object.entries(values)) {
        if (val !== originalValues[key]) {
          updates[key] = val;
        }
      }

      const res = await fetch('/api/env', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: updates }),
      });

      if (res.ok) {
        setSaveStatus('success');
        setSaveMessage('Configuration saved. Rebuild containers with `make build && make up` to apply.');
        // Re-fetch to get updated masked values
        const [envRes, validRes] = await Promise.all([
          fetch('/api/env'),
          fetch('/api/validate'),
        ]);
        const envData = await envRes.json();
        const validData = await validRes.json();
        setValues(envData.values);
        setOriginalValues(envData.values);
        setValidation(validData);
      } else {
        setSaveStatus('error');
        setSaveMessage('Failed to save configuration.');
      }
    } catch (e) {
      setSaveStatus('error');
      setSaveMessage('Network error. Is the config server running?');
    } finally {
      setSaving(false);
    }
  };

  const handlePreset = (presetKey: string) => {
    if (!schema) return;
    const preset = schema.presets[presetKey];
    if (!preset) return;
    setValues((prev) => ({ ...prev, ...preset }));
    setSaveStatus('idle');
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/test-connection', { method: 'POST' });
      const data = await res.json();
      setTestResult(data);
    } catch (e) {
      setTestResult({ success: false, error: 'Network error. Is the config server running?' });
    } finally {
      setTesting(false);
    }
  };

  const hasChanges = JSON.stringify(values) !== JSON.stringify(originalValues);

  const togglePassword = (key: string) => {
    setShowPasswords((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-trident-muted">Loading configuration...</div>
      </div>
    );
  }

  if (!schema) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-red-400">Failed to load configuration schema.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-trident-border bg-trident-surface">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="font-heading text-xl font-bold text-trident-text">Trident Config</h1>
            <p className="text-xs text-trident-muted mt-0.5">Edit LLM providers, agent models, and lab credentials</p>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges}
            className={`btn-primary gap-2 ${!hasChanges ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <Save size={16} />
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </header>

      {/* Status message */}
      {saveStatus !== 'idle' && (
        <div className={`mx-auto max-w-4xl px-6 pt-4`}>
          <div
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm ${
              saveStatus === 'success'
                ? 'bg-emerald-950 text-emerald-200 border border-emerald-700'
                : 'bg-red-950 text-red-200 border border-red-700'
            }`}
          >
            {saveStatus === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
            {saveMessage}
          </div>
        </div>
      )}

      {/* Validation warnings */}
      {validation && !validation.valid && (
        <div className="mx-auto max-w-4xl px-6 pt-4">
          <div className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm bg-amber-950 text-amber-200 border border-amber-700">
            <AlertCircle size={16} />
            Missing required variables: {validation.missing.join(', ')}
          </div>
        </div>
      )}

      {/* Form */}
      <main className="mx-auto max-w-4xl px-6 py-6 space-y-6">
        {/* Provider presets */}
        <div className="card">
          <h2 className="text-sm font-semibold text-trident-text mb-3 flex items-center gap-2">
            <Zap size={16} className="text-trident-accent" />
            Quick Presets
          </h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(schema.presets).map(([key, preset]) => (
              <button
                key={key}
                onClick={() => handlePreset(key)}
                className="btn-ghost text-xs gap-1.5"
              >
                <span className="font-mono">{key}</span>
                <span className="text-trident-muted/50">({preset.LLM_BASE_URL})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Grouped variables */}
        {schema.groups.map((group) => {
          const groupVars = schema.variables.filter((v) => v.group === group.id);
          if (groupVars.length === 0) return null;

          return (
            <div key={group.id} className="card">
              <h2 className="text-base font-semibold text-trident-text mb-1">{group.title}</h2>
              <p className="text-xs text-trident-muted mb-4">{group.description}</p>

              <div className="space-y-4">
                {groupVars.map((v) => (
                  <div key={v.key}>
                    <label className="label">
                      {v.label}
                      {v.required && <span className="text-red-400 ml-1">*</span>}
                    </label>

                    {v.type === 'select' ? (
                      <select
                        value={values[v.key] || ''}
                        onChange={(e) => handleChange(v.key, e.target.value)}
                        className="input-field"
                      >
                        <option value="">Select...</option>
                        {v.options?.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : v.type === 'password' ? (
                      <div className="relative">
                        <input
                          type={showPasswords[v.key] ? 'text' : 'password'}
                          value={values[v.key] || ''}
                          onChange={(e) => handleChange(v.key, e.target.value)}
                          placeholder={v.placeholder}
                          className="input-field pr-10 font-mono"
                        />
                        <button
                          type="button"
                          onClick={() => togglePassword(v.key)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-trident-muted hover:text-trident-text"
                        >
                          {showPasswords[v.key] ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={values[v.key] || ''}
                        onChange={(e) => handleChange(v.key, e.target.value)}
                        placeholder={v.placeholder}
                        className="input-field font-mono text-sm"
                      />
                    )}

                    {v.description && (
                      <p className="text-xs text-trident-muted/70 mt-1">{v.description}</p>
                    )}
                  </div>
                ))}

                {/* Test Connection button — only in the provider group */}
                {group.id === 'provider' && (
                  <div className="pt-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={testing}
                      className="btn-ghost gap-2 text-sm"
                    >
                      {testing ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Plug size={16} />
                      )}
                      {testing ? 'Testing...' : 'Test Connection'}
                    </button>

                    {testResult && (
                      <div
                        className={`mt-3 rounded-lg px-4 py-3 text-sm ${
                          testResult.success
                            ? 'bg-emerald-950 text-emerald-200 border border-emerald-700'
                            : 'bg-red-950 text-red-200 border border-red-700'
                        }`}
                      >
                        {testResult.success ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 font-medium">
                              <CheckCircle size={16} /> Connected
                            </div>
                            <div className="text-xs text-emerald-300">
                              Model: <span className="font-mono">{testResult.model}</span>
                              {' · '}Latency: {testResult.latency_s}s
                            </div>
                            {testResult.reply && (
                              <div className="text-xs text-emerald-300">
                                Response: <span className="font-mono">"{testResult.reply}"</span>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 font-medium">
                              <AlertCircle size={16} /> Connection failed
                            </div>
                            <div className="text-xs text-red-300 font-mono break-all">
                              {testResult.error}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Footer hint */}
        <p className="text-center text-xs text-trident-muted/50 pb-6">
          Changes are saved to <code className="font-mono">.env</code>. Run{' '}
          <code className="font-mono">make build &amp;&amp; make up</code> to apply.
        </p>
      </main>
    </div>
  );
}

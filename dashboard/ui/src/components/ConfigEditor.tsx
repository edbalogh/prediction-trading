// dashboard/ui/src/components/ConfigEditor.tsx
import { useState, useEffect } from "react";
import type { ConfigField, StrategyConfig } from "../types";
import { api } from "../api/client";

interface Props {
  strategyName: string;
  displayName: string;
  isOpen: boolean;
  onClose: () => void;
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: ConfigField;
  value: number | boolean | string;
  onChange: (val: number | boolean | string) => void;
}) {
  if (field.type === "bool") {
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-colors relative ${
          value ? "bg-accent" : "bg-[#d0d0e0]"
        }`}
      >
        <span
          className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
            value ? "translate-x-5" : "translate-x-0.5"
          }`}
        />
      </button>
    );
  }

  const step = field.type === "float" ? "0.01" : "1";
  return (
    <input
      type="number"
      step={step}
      min={field.min}
      max={field.max}
      value={value as number}
      onChange={(e) => {
        const raw = e.target.value;
        const num = field.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
        if (!isNaN(num)) onChange(num);
      }}
      className="w-28 text-right text-[12px] font-mono px-2 py-1 border border-card-border rounded-lg bg-surface text-text-primary focus:outline-none focus:border-accent"
    />
  );
}

export function ConfigEditor({ strategyName, displayName, isOpen, onClose }: Props) {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [values, setValues] = useState<Record<string, number | boolean | string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    api
      .getConfig(strategyName)
      .then((cfg) => {
        setConfig(cfg);
        setValues({ ...cfg.values });
      })
      .catch(() => setError("Failed to load config."));
  }, [isOpen, strategyName]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.putConfig(strategyName, values);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={onClose}
        />
      )}

      {/* Slide-over panel */}
      <div
        className={`fixed top-0 right-0 h-full w-[360px] bg-card shadow-2xl z-50 flex flex-col transition-transform duration-200 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-card-border">
          <div>
            <p className="text-[13px] font-bold text-text-primary">{displayName}</p>
            <p className="text-[10.5px] text-text-muted">Config — saved to disk, takes effect on next start</p>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <p className="text-[11px] text-loss bg-[#fef2f2] border border-[#fecaca] rounded-lg px-3 py-2 mb-4">
              {error}
            </p>
          )}
          {!config && !error && (
            <p className="text-text-muted text-sm text-center py-8">Loading...</p>
          )}
          {config && (
            <div className="space-y-3">
              {config.schema.map((field) => (
                <div key={field.key} className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-[11.5px] font-medium text-text-primary truncate">
                      {field.label}
                    </p>
                    {(field.min !== undefined || field.max !== undefined) && (
                      <p className="text-[10px] text-text-muted">
                        {field.min !== undefined ? `min ${field.min}` : ""}
                        {field.min !== undefined && field.max !== undefined ? " · " : ""}
                        {field.max !== undefined ? `max ${field.max}` : ""}
                      </p>
                    )}
                  </div>
                  <FieldInput
                    field={field}
                    value={values[field.key] ?? field.default}
                    onChange={(val) => setValues((prev) => ({ ...prev, [field.key]: val }))}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-card-border flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 text-[12px] font-semibold py-2 rounded-lg border border-card-border text-text-secondary hover:bg-surface transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !config}
            className="flex-1 text-[12px] font-semibold py-2 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving…" : "Save Config"}
          </button>
        </div>
      </div>
    </>
  );
}

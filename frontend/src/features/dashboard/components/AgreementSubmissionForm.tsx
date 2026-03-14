import { FormEvent, useState } from 'react';

import type { DashboardAnalysisInput } from '../types';

interface AgreementSubmissionFormProps {
  onSubmit: (input: DashboardAnalysisInput) => Promise<void>;
  isSubmitting: boolean;
}

export function AgreementSubmissionForm({ onSubmit, isSubmitting }: AgreementSubmissionFormProps) {
  const [title, setTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [agreedAt, setAgreedAt] = useState('');
  const [termsText, setTermsText] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedSourceUrl = sourceUrl.trim();
    const normalizedTermsText = termsText.trim();

    if (!normalizedSourceUrl && !normalizedTermsText) {
      setFormError('Provide either a source URL or terms text.');
      return;
    }

    setFormError(null);
    await onSubmit({
      title: title.trim() || null,
      source_url: normalizedSourceUrl || null,
      // Backend contracts expect ISO datetime strings.
      agreed_at: agreedAt ? new Date(agreedAt).toISOString() : null,
      terms_text: normalizedTermsText || null,
    });
  };

  return (
    <section className="panel">
      <h2 className="panel-title">Submit Terms and Conditions</h2>
      <p className="muted">
        Enter terms text, a terms URL, or both. The report is generated and saved immediately.
      </p>
      <form className="form-grid" onSubmit={handleSubmit}>
        <label className="field">
          <span>Agreement title</span>
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Example: Acme Cloud Terms of Service"
          />
        </label>
        <label className="field">
          <span>Source URL</span>
          <input
            type="url"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://example.com/terms"
          />
        </label>
        <label className="field">
          <span>Agreed date</span>
          <input
            type="date"
            value={agreedAt}
            onChange={(event) => setAgreedAt(event.target.value)}
          />
        </label>
        <label className="field field-full">
          <span>Terms text</span>
          <textarea
            value={termsText}
            onChange={(event) => setTermsText(event.target.value)}
            placeholder="Paste terms and conditions text..."
            rows={9}
          />
        </label>
        {formError ? (
          <p className="inline-error" role="alert">
            {formError}
          </p>
        ) : null}
        <div className="actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Analyzing...' : 'Analyze and save report'}
          </button>
        </div>
      </form>
    </section>
  );
}

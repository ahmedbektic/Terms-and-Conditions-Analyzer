import { FormEvent, useState } from 'react';

import { sanitizeReportAnalyzeInput } from '../../../lib/security/inputValidation';
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
    try {
      const sanitizedInput = sanitizeReportAnalyzeInput({
        title: title || null,
        source_url: sourceUrl || null,
        // Backend contracts expect ISO datetime strings.
        agreed_at: agreedAt ? new Date(agreedAt).toISOString() : null,
        terms_text: termsText || null,
      });
      setFormError(null);
      await onSubmit(sanitizedInput);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Submission input is invalid.');
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2 className="panel-title">Submit Terms and Conditions</h2>
        <p className="panel-description">
          Enter terms text, a terms URL, or both. The report is generated and saved immediately.
        </p>
      </header>
      <form className="form-grid form-grid-submission" onSubmit={handleSubmit}>
        <label className="field field-compact">
          <span>Agreement title</span>
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Example: Acme Cloud Terms of Service"
            maxLength={200}
          />
        </label>
        <label className="field field-compact">
          <span>Source URL</span>
          <input
            type="url"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://example.com/terms"
            maxLength={2048}
          />
        </label>
        <label className="field field-compact">
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
            maxLength={200000}
          />
        </label>
        <p className="field-help field-full">Provide at least one: source URL or terms text.</p>
        {formError ? (
          <p className="inline-error field-full" role="alert">
            {formError}
          </p>
        ) : null}
        <div className="actions submission-actions field-full">
          <button type="submit" className="button-primary" disabled={isSubmitting}>
            {isSubmitting ? 'Analyzing...' : 'Analyze and save report'}
          </button>
          <p className="submit-hint">
            {isSubmitting
              ? 'Generating summary and clause risk analysis.'
              : 'Reports are saved automatically to your history.'}
          </p>
        </div>
      </form>
    </section>
  );
}

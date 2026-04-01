import { FormEvent, useState } from 'react';

import {
  MAX_SOURCE_URL_LENGTH,
  MAX_TERMS_TEXT_LENGTH,
  MAX_TITLE_LENGTH,
  sanitizeReportAnalyzeInput,
} from '../../../lib/security/inputValidation';
import type { DashboardAnalysisInput } from '../types';

interface AgreementSubmissionFormProps {
  onSubmit: (input: DashboardAnalysisInput) => Promise<void>;
  isSubmitting: boolean;
}

const countFormatter = new Intl.NumberFormat('en-US');

function formatCount(value: number): string {
  return countFormatter.format(value);
}

export function AgreementSubmissionForm({ onSubmit, isSubmitting }: AgreementSubmissionFormProps) {
  const [title, setTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [agreedAt, setAgreedAt] = useState('');
  const [termsText, setTermsText] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const termsCharacterCount = termsText.length;
  const termsCharactersOverLimit = Math.max(termsCharacterCount - MAX_TERMS_TEXT_LENGTH, 0);
  const hasReachedTermsLimit = termsCharacterCount >= MAX_TERMS_TEXT_LENGTH;
  const submitBlockedByTermsLimit = hasReachedTermsLimit;
  const termsLimitMessage =
    termsCharactersOverLimit > 0
      ? `You've exceeded the ${formatCount(MAX_TERMS_TEXT_LENGTH)} character limit by ${formatCount(
          termsCharactersOverLimit,
        )} characters.`
      : hasReachedTermsLimit
        ? `You've reached the ${formatCount(MAX_TERMS_TEXT_LENGTH)} character limit. Shorten the terms text before analyzing.`
        : null;
  const submitDisabledReason = submitBlockedByTermsLimit
    ? termsLimitMessage ?? `Terms text must stay under ${formatCount(MAX_TERMS_TEXT_LENGTH)} characters.`
    : undefined;
  const textareaDescriptionIds = ['terms-text-guidance', 'terms-text-counter'];
  if (termsLimitMessage) {
    textareaDescriptionIds.push('terms-text-limit-message');
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitBlockedByTermsLimit) {
      setFormError(null);
      return;
    }
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
            maxLength={MAX_TITLE_LENGTH}
          />
        </label>
        <label className="field field-compact">
          <span>Source URL</span>
          <input
            type="url"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://example.com/terms"
            maxLength={MAX_SOURCE_URL_LENGTH}
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
            aria-describedby={textareaDescriptionIds.join(' ')}
            aria-invalid={submitBlockedByTermsLimit ? 'true' : undefined}
            className={hasReachedTermsLimit ? 'field-input-limit' : undefined}
            value={termsText}
            onChange={(event) => setTermsText(event.target.value)}
            placeholder="Paste terms and conditions text..."
            rows={9}
          />
        </label>
        <div className="terms-support-row field-full">
          <p className="field-help" id="terms-text-guidance">
            Provide at least one: source URL or terms text.
          </p>
          <p
            className={`field-help terms-character-counter${hasReachedTermsLimit ? ' terms-character-counter-limit' : ''}`}
            id="terms-text-counter"
            aria-live="polite"
          >
            {formatCount(termsCharacterCount)} / {formatCount(MAX_TERMS_TEXT_LENGTH)} characters
          </p>
        </div>
        {termsLimitMessage ? (
          <p className="inline-error field-full" role="alert" id="terms-text-limit-message">
            {termsLimitMessage}
          </p>
        ) : null}
        {formError ? (
          <p className="inline-error field-full" role="alert">
            {formError}
          </p>
        ) : null}
        <div className="actions submission-actions field-full">
          <span className="button-disabled-wrapper" title={submitDisabledReason}>
            <button
              type="submit"
              className="button-primary"
              disabled={isSubmitting || submitBlockedByTermsLimit}
              aria-describedby={termsLimitMessage ? 'terms-text-limit-message' : undefined}
            >
              {isSubmitting ? 'Analyzing...' : 'Analyze and save report'}
            </button>
          </span>
          <p className="submit-hint">
            {submitBlockedByTermsLimit
              ? 'Trim the submitted terms text to re-enable analysis.'
              : isSubmitting
              ? 'Generating summary and clause risk analysis.'
              : 'Reports are saved automatically to your history.'}
          </p>
        </div>
      </form>
    </section>
  );
}

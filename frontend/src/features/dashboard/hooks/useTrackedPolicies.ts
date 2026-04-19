/* Architecture note:
 * This hook owns dashboard watchlist state and keeps tracked-policy network
 * behavior separate from report-analysis state. The dashboard container can
 * compose both hooks without merging unrelated workflows.
 */

import { useCallback, useState } from 'react';

import type { DashboardApiClient } from '../../../lib/api/client';
import { mapTrackedPolicy, mapTrackedPolicyEnrollmentResult } from '../mappers';
import type {
  DashboardTrackedPolicy,
  DashboardTrackedPolicyEnrollmentResult,
} from '../types';

interface UseTrackedPoliciesResult {
  trackedPolicies: DashboardTrackedPolicy[];
  isLoadingTrackedPolicies: boolean;
  isCreatingTrackedPolicy: boolean;
  checkingTrackedPolicyId: string | null;
  removingTrackedPolicyId: string | null;
  errorMessage: string | null;
  successMessage: string | null;
  loadTrackedPolicies: () => Promise<void>;
  createTrackedPolicy: (sourceUrl: string) => Promise<DashboardTrackedPolicyEnrollmentResult | null>;
  checkTrackedPolicy: (trackedPolicyId: string) => Promise<void>;
  removeTrackedPolicy: (trackedPolicyId: string) => Promise<void>;
  clearMessages: () => void;
}

export function useTrackedPolicies(apiClient: DashboardApiClient): UseTrackedPoliciesResult {
  const [trackedPolicies, setTrackedPolicies] = useState<DashboardTrackedPolicy[]>([]);
  const [isLoadingTrackedPolicies, setIsLoadingTrackedPolicies] = useState(false);
  const [isCreatingTrackedPolicy, setIsCreatingTrackedPolicy] = useState(false);
  const [checkingTrackedPolicyId, setCheckingTrackedPolicyId] = useState<string | null>(null);
  const [removingTrackedPolicyId, setRemovingTrackedPolicyId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const clearMessages = useCallback(() => {
    setErrorMessage(null);
    setSuccessMessage(null);
  }, []);

  const loadTrackedPolicies = useCallback(async () => {
    setIsLoadingTrackedPolicies(true);
    setErrorMessage(null);
    try {
      const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
      setTrackedPolicies(trackedPoliciesResponse.map(mapTrackedPolicy));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load your watchlist.');
    } finally {
      setIsLoadingTrackedPolicies(false);
    }
  }, [apiClient]);

  const createTrackedPolicy = useCallback(
    async (sourceUrl: string) => {
      setIsCreatingTrackedPolicy(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const enrollmentResponse = await apiClient.createTrackedPolicy({
          source_url: sourceUrl,
        });
        const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
        setTrackedPolicies(trackedPoliciesResponse.map(mapTrackedPolicy));
        const enrollmentResult = mapTrackedPolicyEnrollmentResult(enrollmentResponse);
        if (enrollmentResult.baselineReportAction === 'created') {
          setSuccessMessage(
            `${enrollmentResult.trackedPolicy.displayName} was analyzed, saved as a baseline report, and added to your watchlist with its first stored version.`,
          );
        } else {
          setSuccessMessage(
            `${enrollmentResult.trackedPolicy.displayName} reused an existing saved baseline report and was added to your watchlist with its first stored version.`,
          );
        }
        return enrollmentResult;
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to add the policy to your watchlist.',
        );
        return null;
      } finally {
        setIsCreatingTrackedPolicy(false);
      }
    },
    [apiClient],
  );

  const checkTrackedPolicy = useCallback(
    async (trackedPolicyId: string) => {
      setCheckingTrackedPolicyId(trackedPolicyId);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const checkedTrackedPolicy = await apiClient.checkTrackedPolicy(trackedPolicyId);
        const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
        setTrackedPolicies(trackedPoliciesResponse.map(mapTrackedPolicy));
        setSuccessMessage(`${checkedTrackedPolicy.display_name} was checked for updates.`);
      } catch (error) {
        try {
          const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
          setTrackedPolicies(trackedPoliciesResponse.map(mapTrackedPolicy));
        } catch {
          // Preserve the last known watchlist state when a refresh fails after the check error.
        }
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to check the policy for updates.',
        );
      } finally {
        setCheckingTrackedPolicyId(null);
      }
    },
    [apiClient],
  );

  const removeTrackedPolicy = useCallback(
    async (trackedPolicyId: string) => {
      setRemovingTrackedPolicyId(trackedPolicyId);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        await apiClient.removeTrackedPolicy(trackedPolicyId);
        const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
        setTrackedPolicies(trackedPoliciesResponse.map(mapTrackedPolicy));
        setSuccessMessage('Policy removed from your watchlist.');
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to remove the policy from your watchlist.',
        );
      } finally {
        setRemovingTrackedPolicyId(null);
      }
    },
    [apiClient],
  );

  return {
    trackedPolicies,
    isLoadingTrackedPolicies,
    isCreatingTrackedPolicy,
    checkingTrackedPolicyId,
    removingTrackedPolicyId,
    errorMessage,
    successMessage,
    loadTrackedPolicies,
    createTrackedPolicy,
    checkTrackedPolicy,
    removeTrackedPolicy,
    clearMessages,
  };
}

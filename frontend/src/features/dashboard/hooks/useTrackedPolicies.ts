/* Architecture note:
 * This hook owns watchlist CRUD plus tracked-policy history/compare state so
 * the dashboard container can switch views without leaking transport details.
 */

import { useCallback, useState } from 'react';

import type { DashboardApiClient } from '../../../lib/api/client';
import {
  mapTrackedPolicy,
  mapTrackedPolicyComparison,
  mapTrackedPolicyEnrollmentResult,
  mapTrackedPolicySnapshot,
} from '../mappers';
import type {
  DashboardTrackedPolicy,
  DashboardTrackedPolicyComparison,
  DashboardTrackedPolicyEnrollmentResult,
  DashboardTrackedPolicySnapshot,
} from '../types';

interface UseTrackedPoliciesResult {
  trackedPolicies: DashboardTrackedPolicy[];
  isLoadingTrackedPolicies: boolean;
  isCreatingTrackedPolicy: boolean;
  checkingTrackedPolicyId: string | null;
  removingTrackedPolicyId: string | null;
  selectedTrackedPolicy: DashboardTrackedPolicy | null;
  trackedPolicySnapshots: DashboardTrackedPolicySnapshot[];
  selectedSnapshotIds: string[];
  trackedPolicyComparison: DashboardTrackedPolicyComparison | null;
  isLoadingTrackedPolicySnapshots: boolean;
  isLoadingTrackedPolicyComparison: boolean;
  errorMessage: string | null;
  successMessage: string | null;
  loadTrackedPolicies: () => Promise<void>;
  createTrackedPolicy: (sourceUrl: string) => Promise<DashboardTrackedPolicyEnrollmentResult | null>;
  checkTrackedPolicy: (trackedPolicyId: string) => Promise<void>;
  removeTrackedPolicy: (trackedPolicyId: string) => Promise<void>;
  openTrackedPolicyHistory: (trackedPolicy: DashboardTrackedPolicy) => Promise<void>;
  closeTrackedPolicyHistory: () => void;
  toggleTrackedPolicySnapshotSelection: (snapshotId: string) => void;
  compareSelectedTrackedPolicySnapshots: () => Promise<void>;
  returnToTrackedPolicyHistory: () => void;
  clearMessages: () => void;
}

export function useTrackedPolicies(apiClient: DashboardApiClient): UseTrackedPoliciesResult {
  const [trackedPolicies, setTrackedPolicies] = useState<DashboardTrackedPolicy[]>([]);
  const [isLoadingTrackedPolicies, setIsLoadingTrackedPolicies] = useState(false);
  const [isCreatingTrackedPolicy, setIsCreatingTrackedPolicy] = useState(false);
  const [checkingTrackedPolicyId, setCheckingTrackedPolicyId] = useState<string | null>(null);
  const [removingTrackedPolicyId, setRemovingTrackedPolicyId] = useState<string | null>(null);
  const [selectedTrackedPolicy, setSelectedTrackedPolicy] = useState<DashboardTrackedPolicy | null>(
    null,
  );
  const [trackedPolicySnapshots, setTrackedPolicySnapshots] = useState<
    DashboardTrackedPolicySnapshot[]
  >([]);
  const [selectedSnapshotIds, setSelectedSnapshotIds] = useState<string[]>([]);
  const [trackedPolicyComparison, setTrackedPolicyComparison] =
    useState<DashboardTrackedPolicyComparison | null>(null);
  const [isLoadingTrackedPolicySnapshots, setIsLoadingTrackedPolicySnapshots] = useState(false);
  const [isLoadingTrackedPolicyComparison, setIsLoadingTrackedPolicyComparison] = useState(false);
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
      const mappedTrackedPolicies = trackedPoliciesResponse.map(mapTrackedPolicy);
      setTrackedPolicies(mappedTrackedPolicies);
      setSelectedTrackedPolicy((currentTrackedPolicy) => {
        if (!currentTrackedPolicy) {
          return null;
        }
        return (
          mappedTrackedPolicies.find(
            (trackedPolicy) => trackedPolicy.id === currentTrackedPolicy.id,
          ) ?? null
        );
      });
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
        const mappedTrackedPolicies = trackedPoliciesResponse.map(mapTrackedPolicy);
        setTrackedPolicies(mappedTrackedPolicies);
        if (selectedTrackedPolicy?.id === trackedPolicyId) {
          setSelectedTrackedPolicy(
            mappedTrackedPolicies.find((trackedPolicy) => trackedPolicy.id === trackedPolicyId) ??
              selectedTrackedPolicy,
          );
        }
        if (checkedTrackedPolicy.latest_capture_message) {
          setSuccessMessage(checkedTrackedPolicy.latest_capture_message);
        } else if (checkedTrackedPolicy.latest_change_status === 'updated') {
          setSuccessMessage(
            `${checkedTrackedPolicy.display_name} was checked and a policy update was detected.`,
          );
        } else if (checkedTrackedPolicy.latest_change_status === 'not_evaluated') {
          setSuccessMessage(
            `${checkedTrackedPolicy.display_name} was checked and stored as its first tracked version.`,
          );
        } else if (checkedTrackedPolicy.latest_change_status === 'unchanged') {
          setSuccessMessage(
            `${checkedTrackedPolicy.display_name} was checked and no meaningful policy changes were detected.`,
          );
        } else if (checkedTrackedPolicy.latest_change_status === 'comparison_incomplete') {
          setSuccessMessage(
            `${checkedTrackedPolicy.display_name} was checked, but the latest comparison could not be completed.`,
          );
        } else {
          const versionLabel =
            checkedTrackedPolicy.snapshot_version_count === 1
              ? '1 stored version'
              : `${checkedTrackedPolicy.snapshot_version_count} stored versions`;
          setSuccessMessage(
            `${checkedTrackedPolicy.display_name} was checked and now has ${versionLabel}.`,
          );
        }
      } catch (error) {
        try {
          const trackedPoliciesResponse = await apiClient.listTrackedPolicies();
          const mappedTrackedPolicies = trackedPoliciesResponse.map(mapTrackedPolicy);
          setTrackedPolicies(mappedTrackedPolicies);
          if (selectedTrackedPolicy) {
            setSelectedTrackedPolicy(
              mappedTrackedPolicies.find(
                (trackedPolicy) => trackedPolicy.id === selectedTrackedPolicy.id,
              ) ?? selectedTrackedPolicy,
            );
          }
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
    [apiClient, selectedTrackedPolicy],
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
        if (selectedTrackedPolicy?.id === trackedPolicyId) {
          setSelectedTrackedPolicy(null);
          setTrackedPolicySnapshots([]);
          setSelectedSnapshotIds([]);
          setTrackedPolicyComparison(null);
        }
        setSuccessMessage('Policy removed from your watchlist.');
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to remove the policy from your watchlist.',
        );
      } finally {
        setRemovingTrackedPolicyId(null);
      }
    },
    [apiClient, selectedTrackedPolicy],
  );

  const openTrackedPolicyHistory = useCallback(
    async (trackedPolicy: DashboardTrackedPolicy) => {
      setSelectedTrackedPolicy(trackedPolicy);
      setTrackedPolicyComparison(null);
      setSelectedSnapshotIds([]);
      setIsLoadingTrackedPolicySnapshots(true);
      setErrorMessage(null);
      try {
        const snapshots = await apiClient.listTrackedPolicySnapshots(trackedPolicy.id);
        setTrackedPolicySnapshots(snapshots.map(mapTrackedPolicySnapshot));
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to load stored version history.',
        );
      } finally {
        setIsLoadingTrackedPolicySnapshots(false);
      }
    },
    [apiClient],
  );

  const closeTrackedPolicyHistory = useCallback(() => {
    setSelectedTrackedPolicy(null);
    setTrackedPolicySnapshots([]);
    setSelectedSnapshotIds([]);
    setTrackedPolicyComparison(null);
    setIsLoadingTrackedPolicyComparison(false);
    setIsLoadingTrackedPolicySnapshots(false);
  }, []);

  const toggleTrackedPolicySnapshotSelection = useCallback((snapshotId: string) => {
    setSelectedSnapshotIds((currentSelection) => {
      if (currentSelection.includes(snapshotId)) {
        return currentSelection.filter((currentSnapshotId) => currentSnapshotId !== snapshotId);
      }
      if (currentSelection.length === 2) {
        return [currentSelection[1], snapshotId];
      }
      return [...currentSelection, snapshotId];
    });
  }, []);

  const compareSelectedTrackedPolicySnapshots = useCallback(async () => {
    if (!selectedTrackedPolicy || selectedSnapshotIds.length !== 2) {
      return;
    }

    setIsLoadingTrackedPolicyComparison(true);
    setErrorMessage(null);
    try {
      const comparison = await apiClient.compareTrackedPolicySnapshots(
        selectedTrackedPolicy.id,
        selectedSnapshotIds[0],
        selectedSnapshotIds[1],
      );
      setTrackedPolicyComparison(mapTrackedPolicyComparison(comparison));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to compare stored versions.');
    } finally {
      setIsLoadingTrackedPolicyComparison(false);
    }
  }, [apiClient, selectedSnapshotIds, selectedTrackedPolicy]);

  const returnToTrackedPolicyHistory = useCallback(() => {
    setTrackedPolicyComparison(null);
  }, []);

  return {
    trackedPolicies,
    isLoadingTrackedPolicies,
    isCreatingTrackedPolicy,
    checkingTrackedPolicyId,
    removingTrackedPolicyId,
    selectedTrackedPolicy,
    trackedPolicySnapshots,
    selectedSnapshotIds,
    trackedPolicyComparison,
    isLoadingTrackedPolicySnapshots,
    isLoadingTrackedPolicyComparison,
    errorMessage,
    successMessage,
    loadTrackedPolicies,
    createTrackedPolicy,
    checkTrackedPolicy,
    removeTrackedPolicy,
    openTrackedPolicyHistory,
    closeTrackedPolicyHistory,
    toggleTrackedPolicySnapshotSelection,
    compareSelectedTrackedPolicySnapshots,
    returnToTrackedPolicyHistory,
    clearMessages,
  };
}

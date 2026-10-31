import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from './useAuth';
import { HumanFeedback } from '../types';

export function useBadCase() {
  const { username, isAuthenticated } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitFeedback = useCallback(
    async (
      reviewId: string,
      feedback: Omit<HumanFeedback, 'reviewer' | 'timestamp'> & {
        bad_clauses?: string[];
        missed_clauses?: string[];
        overall_rating?: number;
        industry?: string;                  // v2
        contract_type_hint?: string;        // v2
      }
    ) => {
      if (!isAuthenticated) {
        setError('未登录');
        return false;
      }
      setSubmitting(true);
      setError(null);
      try {
        await api.submitFeedbackV2(reviewId, {
          ...feedback,
          reviewer: username || '匿名',
          timestamp: new Date().toISOString(),
        });
        return true;
      } catch (err: any) {
        setError(err.message || '提交失败');
        return false;
      } finally {
        setSubmitting(false);
      }
    },
    [username, isAuthenticated]
  );

  return { submitFeedback, submitting, error };
}

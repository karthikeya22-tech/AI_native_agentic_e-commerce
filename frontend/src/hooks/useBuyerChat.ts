import { useState, useCallback } from "react";
import type {
  BuyerChatRequest,
  BuyerChatResponse,
} from "@/types/buyer-chat";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface UseBuyerChatReturn {
  sendMessage: (merchantId: string, message: string) => Promise<BuyerChatResponse>;
  loading: boolean;
  error: string | null;
  resetError: () => void;
}

export function useBuyerChat(): UseBuyerChatReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetError = useCallback(() => setError(null), []);

  const sendMessage = useCallback(
    async (merchantId: string, message: string): Promise<BuyerChatResponse> => {
      setLoading(true);
      setError(null);

      try {
        const body: BuyerChatRequest = {
          merchant_id: merchantId,
          message,
        };

        const response = await fetch(`${API_BASE_URL}/api/v1/buyer/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          const detail =
            errorData?.detail ?? `Request failed (HTTP ${response.status})`;
          throw new Error(detail);
        }

        const data: BuyerChatResponse = await response.json();
        return data;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Unexpected error occurred";
        setError(message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { sendMessage, loading, error, resetError };
}

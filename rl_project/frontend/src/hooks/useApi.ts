import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type AsyncState } from "../types/api";

const configuredInterval = Number(import.meta.env.VITE_POLL_INTERVAL_MS ?? 30_000);

export function useApi<T>(
  request: () => Promise<T>,
  options: { poll?: boolean } = {},
): AsyncState<T> {
  const requestRef = useRef(request);
  requestRef.current = request;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      setData(await requestRef.current());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("Unable to retrieve data."));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (!options.poll || !Number.isFinite(configuredInterval) || configuredInterval <= 0) return;
    const interval = window.setInterval(() => void refresh(), configuredInterval);
    return () => window.clearInterval(interval);
  }, [options.poll, refresh]);

  return { data, error, isLoading, isRefreshing, refresh };
}

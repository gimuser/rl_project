import { ApiError } from "../types/api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function endpoint(path: string) {
  return `${API_BASE_URL}${path}`;
}

const RETRYABLE_STATUSES = new Set([500, 502, 503, 504]);

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const maxAttempts = 3;
  let lastError: ApiError | null = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12_000);

    try {
      const response = await fetch(endpoint(path), {
        ...options,
        headers: {
          Accept: "application/json",
          ...(options.body ? { "Content-Type": "application/json" } : {}),
          ...options.headers,
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        let message = `Request failed (${response.status})`;
        try {
          const payload: unknown = await response.json();
          if (
            typeof payload === "object" &&
            payload !== null &&
            "detail" in payload &&
            typeof payload.detail === "string"
          ) {
            message = payload.detail;
          }
        } catch {
          // Keep the HTTP status message for non-JSON responses.
        }

        const error = new ApiError(message, response.status);
        if (RETRYABLE_STATUSES.has(response.status) && attempt < maxAttempts) {
          lastError = error;
          await new Promise((resolve) => window.setTimeout(resolve, 500 * attempt));
          continue;
        }
        throw error;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) {
        if (
          error.status !== undefined &&
          RETRYABLE_STATUSES.has(error.status) &&
          attempt < maxAttempts
        ) {
          lastError = error;
          await new Promise((resolve) => window.setTimeout(resolve, 500 * attempt));
          continue;
        }
        throw error;
      }

      if (error instanceof DOMException && error.name === "AbortError") {
        if (attempt < maxAttempts) {
          lastError = new ApiError("The API request timed out. Please try again.");
          await new Promise((resolve) => window.setTimeout(resolve, 500 * attempt));
          continue;
        }
        throw new ApiError("The API request timed out. Please try again.");
      }

      if (attempt < maxAttempts) {
        lastError = new ApiError("Unable to reach the API. Please verify that it is running.");
        await new Promise((resolve) => window.setTimeout(resolve, 500 * attempt));
        continue;
      }
      throw new ApiError("Unable to reach the API. Please verify that it is running.");
    } finally {
      window.clearTimeout(timeout);
    }
  }

  throw lastError ?? new ApiError("Unable to reach the API. Please verify that it is running.");
}

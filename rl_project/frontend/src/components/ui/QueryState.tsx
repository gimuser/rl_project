import type { ReactNode } from "react";
import type { AsyncState } from "../../types/api";
import { EmptyState } from "./EmptyState";
import { LoadingBlock } from "./LoadingBlock";

export function QueryState<T>({
  state,
  children,
  empty,
}: {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  empty?: (data: T) => boolean;
}) {
  if (state.isLoading) return <LoadingBlock />;
  if (state.error) {
    return (
      <div className="query-error" role="alert">
        <div>
          <strong>Data unavailable</strong>
          <p>{state.error.message}</p>
        </div>
        <button className="button button--quiet" type="button" onClick={() => void state.refresh()}>
          Retry
        </button>
      </div>
    );
  }
  if (state.data === null || empty?.(state.data)) {
    return <EmptyState title="No data available" description="The API did not return records for this view." />;
  }
  return <>{children(state.data)}</>;
}

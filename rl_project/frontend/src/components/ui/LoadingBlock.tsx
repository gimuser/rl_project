export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="loading-block" aria-label="Loading data" role="status">
      <span className="sr-only">Loading data</span>
      {Array.from({ length: rows }, (_, index) => (
        <span className="loading-block__line" key={index} />
      ))}
    </div>
  );
}

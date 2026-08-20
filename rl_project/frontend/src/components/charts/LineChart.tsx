type Point = { label: string | number; value: number };

export function LineChart({
  points,
  label,
  valueFormatter = (value) => value.toFixed(2),
}: {
  points: Point[];
  label: string;
  valueFormatter?: (value: number) => string;
}) {
  if (points.length === 0) return null;
  const width = 560;
  const height = 200;
  const padding = 18;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coordinates = points.map((point, index) => {
    const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((point.value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  });

  return (
    <div className="line-chart" role="img" aria-label={`${label} line chart`}>
      <div className="line-chart__axis line-chart__axis--top">{valueFormatter(max)}</div>
      <div className="line-chart__axis line-chart__axis--bottom">{valueFormatter(min)}</div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1={padding} x2={width - padding} y1={padding} y2={padding} />
        <line x1={padding} x2={width - padding} y1={height / 2} y2={height / 2} />
        <line x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <polyline points={coordinates.join(" ")} />
        {coordinates.map((coordinate, index) => {
          const [cx, cy] = coordinate.split(",");
          return <circle key={`${coordinate}-${index}`} cx={cx} cy={cy} r="3.5" />;
        })}
      </svg>
      <div className="line-chart__labels">
        <span>{points[0].label}</span>
        <span>{points[points.length - 1].label}</span>
      </div>
    </div>
  );
}

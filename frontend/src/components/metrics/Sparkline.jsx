/**
 * Sparkline — Tiny inline SVG trend line for metric cards.
 *
 * Renders a polyline from an array of numbers with a dot on the last point.
 * Designed to sit next to a metric value/unit at ~64x20px.
 */

const COLORS = {
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#6366f1',
};

const Sparkline = ({ data, status, color, width = 64, height = 20 }) => {
  if (!data || data.length < 2) return null;
  const c = color || COLORS[status] || COLORS.info;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 1;
  const points = data
    .map((v, i) => {
      const x = pad + (i / (data.length - 1)) * (width - 2 * pad);
      const y = pad + (1 - (v - min) / range) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const lastX = pad + ((data.length - 1) / (data.length - 1)) * (width - 2 * pad);
  const lastY = pad + (1 - (data[data.length - 1] - min) / range) * (height - 2 * pad);
  return (
    <svg width={width} height={height} className="flex-shrink-0" viewBox={`0 0 ${width} ${height}`}>
      <polyline
        points={points}
        fill="none"
        stroke={c}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2" fill={c} />
    </svg>
  );
};

export default Sparkline;

# Chart Colors Reference

Color specifications for data visualization in Autonomy.

---

## Forecast Line Colors (Luzmo Charts)

### Line Color Mapping

| Forecast Type | Primary Color | Hex | Style |
|---------------|--------------|-----|-------|
| **Actuals** | Gray-1000 | `#0f1419` | Dotted (5px dash, 5px gap) |
| **AI/ML Base Forecast** | Blue-900 | `#1e3a70` | Solid |
| **AI/ML Unconstrained** | Green-900 | `#14532d` | Solid |
| **Final CDP** | Purple-900 | `#5b21b6` | Solid |
| **Kinaxis Statistical** | Orange-900 | `#9a3412` | Solid |
| **Proposed Plan** | Red-900 | `#991b1b` | Solid |
| **Seasonal Naive** | Yellow-700 | `#d97706` | Solid |

### Chart Properties

- **Line Width:** 2.5px (consistent)
- **Dot Radius:** 3px (small data point markers)
- **Area Fill:** None
- **Stroke Type:** Solid (except Actuals = dotted)

---

## Performance Score Color Scales

### Automation/Performance (Green Scale)

```typescript
>= 80%: #1b5e20 (deep green)
>= 60%: #2e7d32 (medium green)
>= 40%: #43a047 (light green)
< 40%:  #ef9a9a (light red)
```

### Planner Score (Blue Scale)

```typescript
>= 10: #003d82 (deep blue)
>= 5:  #0066cc (medium blue)
>= 0:  #4da6ff (light blue)
>= -5: #ffa726 (orange)
< -5:  #ff9800 (deep orange)
```

### Agent Score (Green Scale)

```typescript
>= 20: #1b5e20 (deep green)
>= 15: #2e7d32
>= 10: #43a047
>= 5:  #66bb6a
>= 0:  #81c784
< 0:   #ef9a9a (light red)
```

---

## Chart Tokens (CSS Variables)

Use these for Recharts components:

| Token | Color | Hex |
|-------|-------|-----|
| `--chart-1` | Light blue | `hsl(220 70% 75%)` |
| `--chart-2` | Medium blue | `hsl(230 70% 55%)` |
| `--chart-3` | Bright blue | `hsl(240 70% 50%)` |
| `--chart-4` | Deep blue | `hsl(245 70% 45%)` |
| `--chart-5` | Very deep blue | `hsl(250 60% 40%)` |

---

## Usage Examples

```tsx
import { getAutomationColor, getPlannerScoreColor, getAgentScoreColor, CHART_COLORS } from '@/lib/chartColors';

// Conditional styling
<div style={{ backgroundColor: getAutomationColor(75) }}>
  75% Automation
</div>

// Recharts line
<Line dataKey="plannerScore" stroke={CHART_COLORS.plannerScore} />

// Chart tokens
<Line dataKey="series1" stroke="var(--chart-1)" />
```

See `luzmo-compact.css` for Luzmo-specific chart styling.

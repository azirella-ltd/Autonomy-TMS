# Visual Hierarchy

Visual weight system for creating clear information hierarchy.

---

## Three-Tier System

### Primary (Highest Visual Weight)

**Usage:** Hero content, main explanations, most important information
**Visual markers:** Prominent borders (3px), emerald accents, large padding (48px), strong shadows

```tsx
<div className="p-12 border-4 border-emerald-500 rounded-lg bg-gradient-to-br from-emerald-50 to-teal-50"
     style={{ boxShadow: '0 8px 24px rgba(15, 126, 72, 0.15)' }}>
  <h2 className="text-2xl font-bold text-emerald-900 mb-4">Primary Section</h2>
  <p className="text-base font-semibold text-emerald-900">
    Most important content goes here
  </p>
</div>
```

### Secondary (Medium Visual Weight)

**Usage:** Supporting questions, exploratory content, secondary information
**Visual markers:** Subtle borders (1px), medium padding (24px), minimal shadows

```tsx
<div className="p-6 border border-emerald-200 rounded-lg bg-white shadow-sm">
  <h3 className="text-lg font-semibold mb-2">Secondary Section</h3>
  <p className="text-sm text-slate-700">
    Supporting information and context
  </p>
</div>
```

### Tertiary (Lowest Visual Weight)

**Usage:** Minor controls, adjustments, least important actions
**Visual markers:** Minimal styling, small padding (16px), only visible on interaction

```tsx
<div className="p-4 border border-slate-200 rounded-md bg-white">
  <Button variant="outline" size="sm">
    Minor Action
  </Button>
</div>
```

---

## Applying the System

```tsx
<div className="space-y-6">
  {/* PRIMARY: Main agent reasoning */}
  <div className="p-12 border-4 border-emerald-500 rounded-lg">
    <h2 className="text-2xl font-bold">Agent Analysis</h2>
    <p>Key insights and recommendations</p>
  </div>

  {/* SECONDARY: Exploration questions */}
  <div className="p-6 border border-emerald-200 rounded-lg">
    <h3 className="text-lg font-medium">What if we...?</h3>
    <p className="text-sm">Scenario exploration</p>
  </div>

  {/* TERTIARY: Adjustment controls */}
  <div className="p-4 border border-slate-200 rounded-md">
    <Button variant="outline" size="sm">Make Changes</Button>
  </div>
</div>
```

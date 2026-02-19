# Design Tokens Reference

Complete reference for all design tokens in the Autonomy Prototype UI kit.

---

## Table of Contents

1. [Color Palette](#color-palette)
2. [Typography](#typography)
3. [Spacing](#spacing)
4. [Border Radius](#border-radius)
5. [Shadows](#shadows)
6. [Animations](#animations)

---

## Color Palette

### Primary Brand Color

**Emerald Green** - The core brand color representing growth, trust, and forward momentum.

| Token | Value | Hex | Usage |
|-------|-------|-----|-------|
| `--primary` | `138 91% 26%` | `#0f7e48` | Main emerald green for primary actions, focus states |
| `--primary-hover` | `133 100% 20%` | `#006633` | Darker emerald for hover states |
| `--primary-foreground` | `0 0% 100%` | `#ffffff` | White text on primary backgrounds |

**Tailwind Usage:**
```tsx
<button className="bg-primary hover:bg-primary-hover text-primary-foreground">
  Primary Button
</button>
```

---

### Base Colors

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--background` | `hsl(0 0% 100%)` (#ffffff) | `hsl(0 0% 4%)` (#0a0a0a) | Page background |
| `--foreground` | `hsl(0 0% 9%)` (#171717) | `hsl(0 0% 97%)` (#f7f7f7) | Primary text color |
| `--card` | `hsl(0 0% 100%)` | `hsl(0 0% 9%)` | Card backgrounds |
| `--card-foreground` | `hsl(0 0% 9%)` | `hsl(0 0% 97%)` | Text on cards |

---

### Secondary & Muted Colors

Light gray tones for subtle elements, disabled states, and secondary content.

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--secondary` | `hsl(0 0% 96%)` (#f5f5f5) | `hsl(0 0% 15%)` (#262626) | Secondary backgrounds |
| `--secondary-foreground` | `hsl(0 0% 9%)` | `hsl(0 0% 97%)` | Text on secondary |
| `--muted` | `hsl(0 0% 96%)` | `hsl(0 0% 15%)` | Muted/disabled elements |
| `--muted-foreground` | `hsl(0 0% 45%)` (#737373) | `hsl(0 0% 55%)` (#8c8c8c) | Secondary text, labels |

**Example:**
```tsx
<p className="text-muted-foreground text-sm">
  Supporting text or subtle information
</p>
```

---

### Status Colors

Colors for communicating different states and messages.

#### Destructive (Errors)

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--destructive` | `hsl(0 84% 60%)` (#f04444) | `hsl(0 63% 31%)` (#8b2020) | Error states, delete actions |
| `--destructive-foreground` | `#ffffff` | `hsl(0 0% 97%)` | Text on destructive backgrounds |

#### Warning

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--warning` | `hsl(45 93% 47%)` (#f0a500) | `hsl(45 93% 47%)` | Warning messages, caution states |
| `--warning-foreground` | `hsl(0 0% 9%)` | `hsl(0 0% 97%)` | Text on warning backgrounds |

#### Info

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--info` | `hsl(221 83% 53%)` (#2563eb) | `hsl(221 50% 60%)` (#5b8ce8) | Informational messages |
| `--info-foreground` | `hsl(0 0% 97%)` | `hsl(0 0% 97%)` | Text on info backgrounds |

**Example:**
```tsx
<Alert variant="destructive">
  <AlertTitle>Error</AlertTitle>
  <AlertDescription>Something went wrong.</AlertDescription>
</Alert>
```

---

### UI Element Colors

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--border` | `hsl(0 0% 90%)` (#e5e5e5) | `hsl(0 0% 15%)` | Element borders |
| `--input` | `hsl(0 0% 96%)` | `hsl(0 0% 18%)` | Input field backgrounds |
| `--ring` | `138 91% 26%` (emerald) | Same | Focus ring color |
| `--accent` | `hsl(0 0% 96%)` | `hsl(0 0% 22%)` | Accent backgrounds (hover states) |

---

### Sidebar Colors

Sidebar-specific color tokens for navigation elements.

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--sidebar-background` | `hsl(0 0% 100%)` | `hsl(0 0% 9%)` | Sidebar background |
| `--sidebar-foreground` | `hsl(0 0% 9%)` | `hsl(0 0% 97%)` | Sidebar text |
| `--sidebar-active` | `hsl(0 0% 96%)` | `hsl(0 0% 15%)` | Active menu item background |
| `--sidebar-active-foreground` | `138 91% 26%` (emerald) | Same | Active menu item text |
| `--sidebar-primary` | `138 91% 26%` | Same | Primary sidebar color |
| `--sidebar-border` | `hsl(0 0% 90%)` | `hsl(0 0% 15%)` | Sidebar borders |

---

### Chart Colors

Blue scale for data visualization (Recharts).

| Token | Value | Hex | Usage |
|-------|-------|-----|-------|
| `--chart-1` | `hsl(220 70% 75%)` | `#9fc5f8` | Light blue - Series 1 |
| `--chart-2` | `hsl(230 70% 55%)` | `#5b8adb` | Medium blue - Series 2 |
| `--chart-3` | `hsl(240 70% 50%)` | `#4166d9` | Bright blue - Series 3 |
| `--chart-4` | `hsl(245 70% 45%)` | `#3954cf` | Deep blue - Series 4 |
| `--chart-5` | `hsl(250 60% 40%)` | `#3d42a3` | Very deep blue - Series 5 |

**Note:** For forecast-specific line colors, see `04-charts/chart-colors-reference.md`.

---

## Typography

### Font Family

**Primary:** Inter (via Google Fonts or Tailwind default sans-serif stack)

### Font Size Scale

| Class | Size | Rem | Pixels | Usage |
|-------|------|-----|--------|-------|
| `text-xs` | xs | 0.75rem | 12px | Fine print, captions |
| `text-sm` | sm | 0.875rem | 14px | Supporting text, labels |
| `text-base` | base | 1rem | 16px | Body text (default) |
| `text-lg` | lg | 1.125rem | 18px | Emphasized body text |
| `text-xl` | xl | 1.25rem | 20px | Small headings |
| `text-2xl` | 2xl | 1.5rem | 24px | Card titles, section headings |
| `text-3xl` | 3xl | 1.875rem | 30px | Page titles |
| `text-4xl` | 4xl | 2.25rem | 36px | Large headings |

### Font Weight Scale

| Class | Weight | Usage |
|-------|--------|-------|
| `font-normal` | 400 | Body text, default |
| `font-medium` | 500 | Interactive elements, subtle emphasis |
| `font-semibold` | 600 | Headings, strong emphasis |
| `font-bold` | 700 | Card titles, primary headings |

### Typography Hierarchy Pattern

Based on Autonomy component usage:

```tsx
// Card Title
<h2 className="text-2xl font-bold tracking-tight">
  Title Text
</h2>

// Supporting Evidence/Secondary
<p className="text-sm text-slate-700">
  Supporting information
</p>

// Exploration/Interactive Questions
<p className="text-[13px] font-medium text-emerald-700">
  Interactive question or prompt
</p>

// Adjustment/Tertiary Controls
<p className="text-xs text-slate-600">
  Tertiary information or controls
</p>

// Muted/Subtle Text
<p className="text-xs text-muted-foreground">
  Subtle text or metadata
</p>
```

---

## Spacing

**Base Unit:** 4px (0.25rem)

### Common Spacing Scale

| Class | Rem | Pixels | Usage |
|-------|-----|--------|-------|
| `gap-1` / `p-1` | 0.25rem | 4px | Minimal spacing |
| `gap-2` / `p-2` | 0.5rem | 8px | Tight spacing (base unit × 2) |
| `gap-3` / `p-3` | 0.75rem | 12px | Small gaps |
| `gap-4` / `p-4` | 1rem | 16px | Standard spacing |
| `gap-6` / `p-6` | 1.5rem | 24px | Medium spacing (cards) |
| `gap-8` / `p-8` | 2rem | 32px | Large spacing |
| `gap-12` / `p-12` | 3rem | 48px | Section spacing (primary content) |

### Component Spacing Patterns

| Section Type | Padding | Internal Spacing | Usage |
|--------------|---------|------------------|-------|
| **PRIMARY** | `p-12` (48px) | `gap-6` (24px) | Hero content, main explanations |
| **SECONDARY** | `p-6` (24px) | `gap-4` (16px) | Questions, supporting info |
| **TERTIARY** | `p-4` (16px) | `gap-3` (12px) | Buttons, minor controls |
| **Card Header** | `p-6` (24px) | `space-y-1.5` | Top of cards |
| **Card Content** | `p-6 pt-0` | Inherits | Card body content |

**Example:**
```tsx
// Primary section
<div className="p-12 space-y-6 border-4 border-emerald-500">
  {/* Main content */}
</div>

// Card with standard spacing
<Card>
  <CardHeader className="p-6">
    <CardTitle className="text-2xl font-bold">Title</CardTitle>
  </CardHeader>
  <CardContent className="p-6 pt-0">
    {/* Content */}
  </CardContent>
</Card>
```

---

## Border Radius

Consistent rounded corners throughout the application.

| Token | Value | Pixels | Usage |
|-------|-------|--------|-------|
| `--radius` | 0.625rem | 10px | Base radius |
| `rounded-lg` | var(--radius) | 10px | Large components (cards, dialogs) |
| `rounded-md` | calc(var(--radius) - 2px) | 8px | Medium components |
| `rounded-sm` | calc(var(--radius) - 4px) | 6px | Small components (buttons) |

**Example:**
```tsx
<Card className="rounded-lg">         {/* 10px radius */}
  <Button className="rounded-sm">     {/* 6px radius */}
    Click Me
  </Button>
</Card>
```

---

## Shadows

Subtle shadows for depth and hierarchy.

### Shadow Scale

| Class | CSS Value | Usage |
|-------|-----------|-------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle for cards |
| `shadow` | `0 1px 3px rgba(0,0,0,0.1)` | Default shadow |
| `shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Moderate depth |
| `shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Large depth |

### Custom Shadows (Autonomy Specific)

**Primary sections:**
```css
box-shadow: 0 8px 24px rgba(15, 126, 72, 0.15); /* Emerald glow */
```

**Secondary sections:**
```css
box-shadow: 0 2px 8px rgba(71, 85, 105, 0.05); /* Minimal shadow */
```

---

## Animations

### Animation Durations

| Duration | Value | Usage |
|----------|-------|-------|
| Fast | 0.2s | Quick transitions (accordion, scale) |
| Medium | 0.3s | Standard transitions (fade, slide) |
| Slow | 2.5s+ | Background effects (pulse) |

### Common Animation Classes

| Class | Keyframe | Duration | Usage |
|-------|----------|----------|-------|
| `animate-accordion-down` | accordion-down | 0.2s | Accordion expansion |
| `animate-accordion-up` | accordion-up | 0.2s | Accordion collapse |
| `animate-fade-in` | text-appear | 0.3s | Fade in entrance |
| `animate-slide-up` | slide-up | 0.3s | Slide up entrance |
| `animate-scale-in` | scale-in | 0.2s | Scale entrance |
| `animate-pulse-subtle` | pulse-subtle | 2.5s | Subtle pulsing (custom) |

### Custom Animations

**Subtle Pulse:**
```css
@keyframes pulse-subtle {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.02); }
}
```

**Usage:**
```tsx
<div className="animate-pulse-subtle">
  Pulsing element
</div>
```

---

## Design Token Best Practices

### Do's ✅

- **Always use design tokens** instead of hard-coded values
- **Reference CSS variables** in custom components for theme consistency
- **Use Tailwind classes** for spacing, colors, and typography
- **Maintain visual hierarchy** with the 80-15-5 pattern (primary/secondary/tertiary)
- **Test in both light and dark mode**

### Don'ts ❌

- **Don't use arbitrary values** like `bg-[#ff0000]` unless absolutely necessary
- **Don't hard-code colors** in custom CSS
- **Don't mix spacing units** (stick to the 4px base unit)
- **Don't create custom animations** without checking if one exists
- **Don't override design tokens** without understanding the impact

---

## Quick Reference

### Most Common Patterns

```tsx
// Primary Button
<Button className="bg-primary hover:bg-primary-hover text-primary-foreground">
  Action
</Button>

// Secondary Button
<Button variant="outline" className="border-border hover:bg-accent">
  Cancel
</Button>

// Card with Standard Spacing
<Card className="rounded-lg shadow-sm">
  <CardHeader className="p-6">
    <CardTitle className="text-2xl font-bold">Title</CardTitle>
    <CardDescription className="text-sm text-muted-foreground">
      Description
    </CardDescription>
  </CardHeader>
  <CardContent className="p-6 pt-0">
    Content
  </CardContent>
</Card>

// Status Badge
<Badge variant="destructive">Error</Badge>
<Badge className="bg-warning text-warning-foreground">Warning</Badge>
<Badge className="bg-info text-info-foreground">Info</Badge>

// Muted Text
<p className="text-sm text-muted-foreground">
  Secondary information
</p>
```

---

## Additional Resources

- See `../02-components/` for component usage examples
- See `../03-patterns/` for layout and visual hierarchy patterns
- See `../04-charts/` for data visualization colors
- See `QUICK-REFERENCE.md` for one-page cheat sheet

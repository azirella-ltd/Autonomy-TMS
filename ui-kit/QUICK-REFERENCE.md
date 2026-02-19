# Autonomy UI Kit - Quick Reference

One-page cheat sheet for rapid development.

---

## Colors

| Usage | Class | Example |
|-------|-------|---------|
| Primary button | `bg-primary text-primary-foreground` | `<Button className="bg-primary">` |
| Secondary button | `bg-secondary` | `<Button variant="secondary">` |
| Destructive | `bg-destructive text-destructive-foreground` | `<Button variant="destructive">` |
| Muted text | `text-muted-foreground` | `<p className="text-muted-foreground">` |
| Border | `border-border` | `<div className="border border-border">` |

---

## Typography

| Element | Class | Size |
|---------|-------|------|
| Hero | `text-4xl font-bold` | 36px |
| Page title | `text-3xl font-bold` | 30px |
| Card title | `text-2xl font-bold` | 24px |
| Heading | `text-xl font-semibold` | 20px |
| Body | `text-base` | 16px |
| Small | `text-sm` | 14px |
| Caption | `text-xs text-muted-foreground` | 12px |

---

## Spacing

```tsx
p-4   // 16px padding
p-6   // 24px padding
p-12  // 48px padding

gap-3 // 12px gap
gap-4 // 16px gap
gap-6 // 24px gap

space-y-4  // 16px vertical spacing
space-y-6  // 24px vertical spacing
```

---

## Components

### Button

```tsx
<Button variant="default">Primary</Button>
<Button variant="outline">Secondary</Button>
<Button variant="ghost">Tertiary</Button>
<Button variant="destructive">Delete</Button>
<Button size="sm">Small</Button>
<Button size="lg">Large</Button>
```

### Card

```tsx
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Subtitle</CardDescription>
  </CardHeader>
  <CardContent>{/* Content */}</CardContent>
  <CardFooter>{/* Actions */}</CardFooter>
</Card>
```

### Badge

```tsx
<Badge>Default</Badge>
<Badge variant="secondary">Secondary</Badge>
<Badge variant="destructive">Error</Badge>
<Badge variant="outline">Outline</Badge>
```

---

## Layouts

### Grid

```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
  {/* 3-column grid on desktop */}
</div>
```

### Flex

```tsx
<div className="flex items-center justify-between gap-4">
  {/* Horizontal layout with space between */}
</div>
```

---

## Common Patterns

### KPI Card

```tsx
<Card>
  <CardHeader className="p-6">
    <CardDescription>Metric Name</CardDescription>
    <CardTitle className="text-3xl">1,234</CardTitle>
  </CardHeader>
  <CardContent className="p-6 pt-0">
    <p className="text-sm text-emerald-600">+12%</p>
  </CardContent>
</Card>
```

### Form Field

```tsx
<div className="space-y-2">
  <Label htmlFor="name">Name</Label>
  <Input id="name" placeholder="John Doe" />
</div>
```

### Alert

```tsx
<Alert variant="destructive">
  <AlertTitle>Error</AlertTitle>
  <AlertDescription>Message</AlertDescription>
</Alert>
```

---

## Utilities

```tsx
import { cn } from '@/lib/utils/cn';

// Merge classes
<div className={cn("base-class", conditional && "active-class")} />

// Get CSS variable
import { getCSSVariable } from '@/lib/utils/cn';
const primaryColor = getCSSVariable('primary');

// Chart colors
import { getAutomationColor } from '@/lib/utils/chartColors';
const color = getAutomationColor(75);
```

---

## Do's & Don'ts

### ✅ Do

- Use design tokens (`text-primary` instead of `text-[#0f7e48]`)
- Follow spacing scale (4px base unit)
- Use `cn()` utility for conditional classes
- Test in both light and dark mode

### ❌ Don't

- Hard-code colors or spacing
- Mix arbitrary values with design tokens
- Override component styles without understanding impact
- Forget to add `@/` path alias in tsconfig.json

---

## File Paths

```
02-components/ui/          # shadcn components
02-components/custom/      # Autonomy components
02-components/utils/       # Utilities
01-design-tokens/          # Design tokens
03-patterns/               # Examples
04-charts/                 # Chart config
```

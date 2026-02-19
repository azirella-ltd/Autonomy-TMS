# Layout Patterns

Common layout patterns used in the Autonomy Prototype.

---

## Card-Based Layouts

### Basic Card

```tsx
<Card className="rounded-lg shadow-sm">
  <CardHeader className="p-6">
    <CardTitle className="text-2xl font-bold">Card Title</CardTitle>
    <CardDescription className="text-sm text-muted-foreground">
      Optional description
    </CardDescription>
  </CardHeader>
  <CardContent className="p-6 pt-0">
    <p>Card content goes here</p>
  </CardContent>
</Card>
```

### Card with Footer Actions

```tsx
<Card>
  <CardHeader>
    <CardTitle>Confirm Action</CardTitle>
  </CardHeader>
  <CardContent>
    <p>Are you sure you want to proceed?</p>
  </CardContent>
  <CardFooter className="flex justify-end gap-2">
    <Button variant="outline">Cancel</Button>
    <Button>Confirm</Button>
  </CardFooter>
</Card>
```

---

## Grid Layouts

### Two-Column Grid

```tsx
<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
  <Card>Column 1</Card>
  <Card>Column 2</Card>
</div>
```

### Three-Column Grid (KPI Dashboard)

```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
  <KPICard title="Metric 1" value="123" />
  <KPICard title="Metric 2" value="456" />
  <KPICard title="Metric 3" value="789" />
</div>
```

---

## Responsive Breakpoints

Use Tailwind's responsive prefixes:

```tsx
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
  {/* Responsive grid:
      Mobile: 1 column
      Small: 2 columns
      Large: 3 columns
      XL: 4 columns
  */}
</div>
```

---

## Dashboard Layout

```tsx
<div className="container max-w-[1400px] mx-auto p-8">
  {/* Header */}
  <div className="mb-8">
    <h1 className="text-3xl font-bold">Dashboard</h1>
    <p className="text-muted-foreground">Welcome back!</p>
  </div>

  {/* KPI Row */}
  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
    <KPICard />
    <KPICard />
    <KPICard />
  </div>

  {/* Main Content */}
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <Card className="lg:col-span-2">
      {/* Main chart/content */}
    </Card>
    <Card>
      {/* Sidebar content */}
    </Card>
  </div>
</div>
```

# Component Inventory

Complete list of all components in the Autonomy UI kit.

---

## shadcn-ui Components (48)

All components are based on [shadcn/ui](https://ui.shadcn.com) and built with Radix UI primitives.

### Layout Components

| Component | File | Purpose |
|-----------|------|---------|
| Accordion | `ui/accordion.tsx` | Collapsible content sections |
| Card | `ui/card.tsx` | Content container with header/footer |
| Collapsible | `ui/collapsible.tsx` | Expandable/collapsible content |
| Resizable | `ui/resizable.tsx` | Resizable panels/sections |
| Scroll Area | `ui/scroll-area.tsx` | Custom scrollable area |
| Separator | `ui/separator.tsx` | Visual divider line |
| Tabs | `ui/tabs.tsx` | Tabbed content interface |
| Sidebar | `ui/sidebar.tsx` | Navigation sidebar component |
| Aspect Ratio | `ui/aspect-ratio.tsx` | Maintain aspect ratio containers |

### Navigation Components

| Component | File | Purpose |
|-----------|------|---------|
| Breadcrumb | `ui/breadcrumb.tsx` | Breadcrumb navigation trail |
| Menubar | `ui/menubar.tsx` | Horizontal menu bar |
| Navigation Menu | `ui/navigation-menu.tsx` | Dropdown navigation menu |
| Pagination | `ui/pagination.tsx` | Page navigation controls |

### Form Components

| Component | File | Purpose |
|-----------|------|---------|
| Button | `ui/button.tsx` | Interactive button with variants |
| Checkbox | `ui/checkbox.tsx` | Checkbox input |
| Form | `ui/form.tsx` | Form wrapper with React Hook Form integration |
| Input | `ui/input.tsx` | Text input field |
| Input OTP | `ui/input-otp.tsx` | One-time password input |
| Label | `ui/label.tsx` | Form field label |
| Radio Group | `ui/radio-group.tsx` | Radio button group |
| Select | `ui/select.tsx` | Dropdown select menu |
| Slider | `ui/slider.tsx` | Range slider input |
| Switch | `ui/switch.tsx` | Toggle switch |
| Textarea | `ui/textarea.tsx` | Multi-line text input |
| Toggle | `ui/toggle.tsx` | Toggle button |
| Toggle Group | `ui/toggle-group.tsx` | Group of toggle buttons |

### Dialog/Overlay Components

| Component | File | Purpose |
|-----------|------|---------|
| Alert Dialog | `ui/alert-dialog.tsx` | Modal confirmation dialog |
| Context Menu | `ui/context-menu.tsx` | Right-click context menu |
| Dialog | `ui/dialog.tsx` | Modal dialog |
| Drawer | `ui/drawer.tsx` | Sliding drawer overlay |
| Dropdown Menu | `ui/dropdown-menu.tsx` | Dropdown menu |
| Hover Card | `ui/hover-card.tsx` | Hover-triggered popover |
| Popover | `ui/popover.tsx` | Floating popover |
| Sheet | `ui/sheet.tsx` | Slide-out sheet (mobile drawer) |
| Tooltip | `ui/tooltip.tsx` | Hover tooltip |

### Display Components

| Component | File | Purpose |
|-----------|------|---------|
| Alert | `ui/alert.tsx` | Status/notification alert |
| Avatar | `ui/avatar.tsx` | User avatar image |
| Badge | `ui/badge.tsx` | Status badge/tag |
| Calendar | `ui/calendar.tsx` | Date picker calendar |
| Carousel | `ui/carousel.tsx` | Image/content carousel |
| Command | `ui/command.tsx` | Command palette/search |
| Progress | `ui/progress.tsx` | Progress bar |
| Skeleton | `ui/skeleton.tsx` | Loading placeholder |
| Table | `ui/table.tsx` | Data table |
| Toast | `ui/toast.tsx` | Toast notification |
| Toaster | `ui/toaster.tsx` | Toast notification container |

### Chart Components

| Component | File | Purpose |
|-----------|------|---------|
| Chart | `ui/chart.tsx` | Recharts wrapper with theme support |

### Utilities

| File | Purpose |
|------|---------|
| `ui/use-toast.ts` | Toast notification hook |

---

## Custom Autonomy Components (4)

Components specific to the Autonomy.

| Component | File | Purpose | Props |
|-----------|------|---------|-------|
| **SKU Detail Panel** | `custom/SKUDetailPanel.tsx` | Multi-context product detail sidebar | `isDPWorkflow`, `isValidationDetail`, `showBackButton`, `customerAlignmentFlags` |
| **KPI Card** | `custom/KPICard.tsx` | Metric display card | `icon`, `iconColor`, `title`, `value`, `subtitle`, `actionText`, `onAction` |
| **Agent Report Panel** | `custom/AgentReportPanel.tsx` | AI-generated insights panel | (varies) |
| **Forecast Table** | `custom/ForecastTable.tsx` | Editable forecast data table | (varies) |

---

## Utility Functions (2)

| File | Purpose |
|------|---------|
| `utils/cn.ts` | Class name merging utility (clsx + tailwind-merge), CSS variable getter, chart color getter |
| `utils/chartColors.ts` | Chart color mapping functions (automation, performance scores) |

---

## Usage Examples

### Basic Components

```tsx
// Button variants
<Button variant="default">Primary Action</Button>
<Button variant="outline">Secondary Action</Button>
<Button variant="ghost">Tertiary Action</Button>
<Button variant="destructive">Delete</Button>

// Card with header
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>
    Content goes here
  </CardContent>
  <CardFooter>
    <Button>Action</Button>
  </CardFooter>
</Card>

// Alert
<Alert variant="destructive">
  <AlertTitle>Error</AlertTitle>
  <AlertDescription>Something went wrong.</AlertDescription>
</Alert>

// Badge
<Badge>Default</Badge>
<Badge variant="secondary">Secondary</Badge>
<Badge variant="destructive">Error</Badge>
<Badge variant="outline">Outline</Badge>
```

### Form Components

```tsx
import { useForm } from "react-hook-form";

<Form {...form}>
  <form onSubmit={form.handleSubmit(onSubmit)}>
    <FormField
      control={form.control}
      name="email"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Email</FormLabel>
          <FormControl>
            <Input placeholder="email@example.com" {...field} />
          </FormControl>
          <FormDescription>
            We'll never share your email.
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
    <Button type="submit">Submit</Button>
  </form>
</Form>
```

### Custom Components

```tsx
// KPI Card
<KPICard
  icon={TrendingUp}
  iconColor="primary"
  title="Automation Rate"
  value="75%"
  subtitle="Up from 68% last month"
  actionText="View Details"
  onAction={() => navigate('/details')}
/>

// SKU Detail Panel (adaptive based on context)
<SKUDetailPanel
  isDPWorkflow={true}
  showBackButton={false}
  customerAlignmentFlags={flags}
/>
```

---

## Dependencies

All components require these peer dependencies:

```json
{
  "react": "^18.0.0",
  "react-dom": "^18.0.0",
  "@radix-ui/react-*": "latest",
  "class-variance-authority": "^0.7.0",
  "clsx": "^2.0.0",
  "tailwind-merge": "^2.0.0",
  "tailwindcss-animate": "^1.0.7"
}
```

For charts:
```json
{
  "recharts": "^2.10.0"
}
```

For forms:
```json
{
  "react-hook-form": "^7.48.0",
  "@hookform/resolvers": "^3.3.2",
  "zod": "^3.22.4"
}
```

---

## Component Categories Summary

| Category | Count | Purpose |
|----------|-------|---------|
| Layout | 9 | Structure and organization |
| Navigation | 4 | Site navigation |
| Forms | 13 | User input |
| Dialogs/Overlays | 9 | Modal interactions |
| Display | 11 | Information display |
| Charts | 1 | Data visualization |
| Custom (Autonomy) | 4 | Domain-specific components |
| **Total** | **51** | Complete UI component library |

---

## Next Steps

1. See `../01-design-tokens/` for styling configuration
2. See `../03-patterns/` for layout and usage patterns
3. See `00-GETTING-STARTED.md` for installation instructions
4. See `QUICK-REFERENCE.md` for quick lookup guide

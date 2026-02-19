# UI Kit Migration Guide

This guide explains how to migrate existing pages from MUI/Chakra UI to the new Autonomy UI Kit.

## Overview

The Autonomy UI Kit is based on:
- **Tailwind CSS** for styling
- **shadcn/ui** components (Radix UI primitives)
- **lucide-react** for icons

## Quick Reference

### Import Changes

```jsx
// OLD (MUI)
import { Box, Typography, Button, Card } from '@mui/material';
import { Info as InfoIcon } from '@mui/icons-material';

// NEW (Autonomy UI Kit)
import { Card, Button, Alert, Typography } from '../components/common';
import { Info } from 'lucide-react';
```

### Component Mappings

| MUI/Chakra Component | Autonomy UI Kit Equivalent | Import Path |
|---------------------|----------------------|-------------|
| `Box` | `<div className="...">` | Native HTML + Tailwind |
| `Typography` | `Typography` | `../components/common` |
| `Button` | `Button` | `../components/common` |
| `Card` / `Paper` | `Card` | `../components/common` |
| `Alert` | `Alert` | `../components/common` |
| `Chip` | `Badge` / `Chip` | `../components/common` |
| `CircularProgress` | `Spinner` | `../components/common` |
| `Table` | `Table` | `../components/common` |
| `TextField` / `Input` | `Input` | `../components/common` |

### Layout Components

```jsx
// OLD (MUI)
<Box sx={{ display: 'flex', gap: 2, p: 4 }}>
  <Box sx={{ flex: 1 }}>Content</Box>
</Box>

// NEW (Tailwind)
<div className="flex gap-4 p-4">
  <div className="flex-1">Content</div>
</div>
```

### Spacing Reference

| MUI `sx` prop | Tailwind class |
|--------------|----------------|
| `p: 1` (4px) | `p-1` |
| `p: 2` (8px) | `p-2` |
| `p: 3` (12px) | `p-3` |
| `p: 4` (16px) | `p-4` |
| `p: 6` (24px) | `p-6` |
| `p: 8` (32px) | `p-8` |
| `gap: 2` | `gap-2` |
| `mt: 4` | `mt-4` |

### Typography Variants

```jsx
// OLD (MUI)
<Typography variant="h1">Heading</Typography>
<Typography variant="body2" color="text.secondary">Text</Typography>

// NEW (Autonomy UI Kit)
<Typography variant="h1">Heading</Typography>
<Typography variant="body2" color="textSecondary">Text</Typography>

// Or using Tailwind directly
<h1 className="text-4xl font-bold">Heading</h1>
<p className="text-sm text-muted-foreground">Text</p>
```

### Button Variants

```jsx
// OLD (MUI)
<Button variant="contained">Primary</Button>
<Button variant="outlined">Secondary</Button>
<Button variant="text">Text</Button>

// NEW (Autonomy UI Kit)
<Button variant="default">Primary</Button>
<Button variant="outline">Secondary</Button>
<Button variant="ghost">Text</Button>
```

### Card Components

```jsx
// OLD (Chakra)
<Card>
  <CardHeader>
    <Heading size="md">Title</Heading>
  </CardHeader>
  <CardBody>Content</CardBody>
</Card>

// NEW (Autonomy UI Kit)
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>Content</CardContent>
</Card>
```

### Alert/Notification

```jsx
// OLD (MUI)
<Alert severity="error">Error message</Alert>
<Alert severity="success">Success message</Alert>

// NEW (Autonomy UI Kit)
<Alert variant="error">Error message</Alert>
<Alert variant="success">Success message</Alert>
```

### Icons

```jsx
// OLD (MUI Icons)
import { Dashboard, Settings, Person } from '@mui/icons-material';

// NEW (lucide-react)
import { LayoutDashboard, Settings, User } from 'lucide-react';
```

Common icon mappings:
| MUI Icon | lucide-react |
|----------|--------------|
| `Dashboard` | `LayoutDashboard` |
| `Settings` | `Settings` |
| `Person` | `User` |
| `Add` | `Plus` |
| `Edit` | `Pencil` |
| `Delete` | `Trash2` |
| `Search` | `Search` |
| `Close` | `X` |
| `Menu` | `Menu` |
| `ChevronLeft` | `ChevronLeft` |
| `ExpandMore` | `ChevronDown` |
| `Info` | `Info` |
| `Warning` | `AlertTriangle` |
| `Error` | `AlertCircle` |
| `CheckCircle` | `CheckCircle2` |

## Migration Steps

### Step 1: Update Imports

Replace MUI/Chakra imports with Autonomy UI Kit imports:

```jsx
// At the top of the file
import { Card, CardHeader, CardTitle, CardContent, Button, Alert, Badge, Spinner } from '../components/common';
import { cn } from '../lib/utils/cn';
import { LayoutDashboard, Settings, User } from 'lucide-react';
```

### Step 2: Replace Layout Components

Replace MUI `Box` with `div` and Tailwind classes:

```jsx
// Before
<Box sx={{ display: 'flex', flexDirection: 'column', gap: 4, p: 4 }}>

// After
<div className="flex flex-col gap-4 p-4">
```

### Step 3: Replace UI Components

Replace component by component:

```jsx
// Before
<Button variant="contained" onClick={handleClick}>
  <AddIcon /> Add Item
</Button>

// After
<Button onClick={handleClick} leftIcon={<Plus className="h-4 w-4" />}>
  Add Item
</Button>
```

### Step 4: Update Color References

Use CSS variables instead of MUI theme colors:

```jsx
// Before
sx={{ color: 'primary.main', backgroundColor: 'grey.100' }}

// After
className="text-primary bg-muted"
```

### Step 5: Test & Iterate

After migration:
1. Check visual appearance
2. Test interactive elements
3. Verify responsive behavior
4. Test dark mode (if applicable)

## Example Migration

### Before (MUI/Chakra)

```jsx
import { Box, Card, CardHeader, CardBody, Text, Button, Spinner, Alert } from '@chakra-ui/react';
import { Add as AddIcon } from '@mui/icons-material';

const MyPage = () => {
  const [loading, setLoading] = useState(false);

  return (
    <Box p={4}>
      {loading && <Spinner />}
      <Card>
        <CardHeader>
          <Text fontSize="xl" fontWeight="bold">My Card</Text>
        </CardHeader>
        <CardBody>
          <Text color="gray.600">Some content here</Text>
          <Button colorScheme="green" leftIcon={<AddIcon />}>
            Add Item
          </Button>
        </CardBody>
      </Card>
    </Box>
  );
};
```

### After (Autonomy UI Kit)

```jsx
import { Card, CardHeader, CardTitle, CardContent, Button, Spinner } from '../components/common';
import { Plus } from 'lucide-react';

const MyPage = () => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="p-4">
      {loading && <Spinner />}
      <Card>
        <CardHeader>
          <CardTitle>My Card</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Some content here</p>
          <Button leftIcon={<Plus className="h-4 w-4" />}>
            Add Item
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
```

## Files Structure

```
src/
├── components/
│   ├── common/           # Autonomy UI Kit wrapper components
│   │   ├── index.js      # Export all components
│   │   ├── Card.jsx
│   │   ├── Button.jsx
│   │   ├── Alert.jsx
│   │   ├── Badge.jsx
│   │   ├── Input.jsx
│   │   ├── Loading.jsx
│   │   ├── Typography.jsx
│   │   └── Table.jsx
│   ├── ui/               # shadcn/ui components (raw)
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   └── ...
│   ├── AppSidebar.jsx    # New sidebar
│   ├── TopNavbar.jsx     # New navbar
│   └── Layout.jsx        # Main layout
├── lib/
│   └── utils/
│       ├── cn.ts         # Class name utility
│       └── chartColors.ts
└── index.css             # CSS variables & Tailwind
```

## Tips

1. **Migrate incrementally** - Don't try to convert everything at once
2. **Start with layouts** - Convert Layout, Navbar, Sidebar first
3. **Use common components** - They provide familiar APIs
4. **Test dark mode** - CSS variables handle theming
5. **Keep both systems** - MUI and Autonomy UI Kit can coexist during migration

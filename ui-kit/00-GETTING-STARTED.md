# Getting Started with Autonomy UI Kit

Complete integration guide for the Autonomy UI kit.

---

## Prerequisites

- **React**: 18.0.0 or higher
- **Tailwind CSS**: 3.4.0 or higher
- **TypeScript**: 5.0.0 or higher (recommended)
- **Node.js**: 18.0.0 or higher

---

## Installation Steps

### Step 1: Install Dependencies

```bash
npm install -D tailwindcss postcss autoprefixer
npm install clsx tailwind-merge class-variance-authority
npm install tailwindcss-animate

# For components
npm install @radix-ui/react-*  # Install specific Radix components as needed

# For forms (optional)
npm install react-hook-form @hookform/resolvers zod

# For charts (optional)
npm install recharts lucide-react
```

### Step 2: Configure Tailwind

Replace your `tailwind.config.ts` with the one from `01-design-tokens/tailwind.config.ts`:

```bash
cp ui-kit/01-design-tokens/tailwind.config.ts ./tailwind.config.ts
```

Or manually merge the theme configuration if you have existing customizations.

### Step 3: Add CSS Variables

Replace your main CSS file (e.g., `src/index.css` or `app/globals.css`) with `01-design-tokens/globals.css`:

```bash
cp ui-kit/01-design-tokens/globals.css ./src/index.css
```

### Step 4: Copy Components

Copy the component library to your project:

```bash
# Copy all shadcn UI components
cp -r ui-kit/02-components/ui ./src/components/ui

# Copy custom components (optional)
cp -r ui-kit/02-components/custom ./src/components/custom

# Copy utilities
cp -r ui-kit/02-components/utils ./src/lib/
```

### Step 5: Verify Installation

Create a test component to verify everything works:

```tsx
// src/App.tsx or src/pages/index.tsx
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

export default function App() {
  return (
    <div className="container mx-auto p-8">
      <Card>
        <CardHeader>
          <CardTitle>UI Kit Test</CardTitle>
        </CardHeader>
        <CardContent>
          <Button>Click Me</Button>
        </CardContent>
      </Card>
    </div>
  );
}
```

---

## Project Structure

After installation, your project should look like this:

```
your-project/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn components
│   │   └── custom/          # Autonomy custom components (optional)
│   ├── lib/
│   │   └── utils/
│   │       ├── cn.ts        # Class name utility
│   │       └── chartColors.ts  # Chart color utilities
│   └── index.css            # CSS variables
├── tailwind.config.ts       # Tailwind configuration
└── package.json
```

---

## Customization

### Changing Primary Color

Edit `src/index.css`:

```css
:root {
  --primary: 138 91% 26%;  /* Change this HSL value */
}
```

### Adding New Components

1. Browse [shadcn/ui](https://ui.shadcn.com)
2. Copy component code to `src/components/ui/`
3. Install required Radix UI dependencies

### Extending the System

You can add new design tokens in `tailwind.config.ts`:

```typescript
theme: {
  extend: {
    colors: {
      'brand-blue': 'hsl(221 83% 53%)',
    },
  },
}
```

---

## Dark Mode

Dark mode is enabled by default. Toggle it by adding the `dark` class to your root element:

```tsx
// Example with state
const [darkMode, setDarkMode] = useState(false);

return (
  <div className={darkMode ? 'dark' : ''}>
    <App />
  </div>
);
```

---

## Troubleshooting

### Issue: "Module not found: @/components/ui/button"

**Solution:** Configure path aliases in `tsconfig.json`:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

For Vite, add to `vite.config.ts`:

```typescript
import path from "path"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
```

### Issue: "Tailwind classes not applying"

**Solution:**
1. Ensure `@tailwind` directives are in your CSS file
2. Verify `content` paths in `tailwind.config.ts` include your files
3. Restart your dev server

### Issue: "Components look unstyled"

**Solution:** Ensure you've copied both `tailwind.config.ts` AND `globals.css`

---

## Next Steps

- 📖 Read `01-design-tokens/tokens-reference.md` for design system documentation
- 🎨 Browse `03-patterns/` for layout examples
- 📊 Check `04-charts/` for data visualization setup
- ⚡ See `QUICK-REFERENCE.md` for quick lookup

---

## Support

For issues or questions:
- Check component documentation in `02-components/components-inventory.md`
- Review pattern examples in `03-patterns/`
- Refer to [shadcn/ui docs](https://ui.shadcn.com)

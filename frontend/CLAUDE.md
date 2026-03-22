# Frontend — Claude Code Context

Scoped instructions for working in the frontend. Supplements the root CLAUDE.md.

## Stack
- React 18, Tailwind CSS, shadcn/ui components, lucide-react icons
- Recharts for charts, react-markdown for Markdown rendering
- Zustand for tab state (`stores/useTabStore.js`)
- Axios via `services/api.js` (all calls go through Nginx proxy at `/api/*`)

## Architecture

### Tabbed Workspace Shell
The app uses a tabbed workspace (like VS Code/Claude Code):
- `WorkspaceShell.jsx` — replaces the old Layout; renders TopNavbar + TabBar + TabPanes
- `TabBar.jsx` — tab strip with pinned Decision Stream, closeable tabs, `+` palette
- `TabPane.jsx` — `display:block/none` wrapper preserving component state
- `useTabStore.js` — Zustand store for tab management (sessionStorage persistence)
- `NewTabPalette.jsx` — searchable command palette for opening pages in tabs

### Azirella (AI Assistant)
- `AzirellaAvatar.jsx` — animated avatar with voice state colors, supports `inline` mode
- `useVoiceAssistant.js` — Web Speech API hook with wake words ("Hi Azirella", "Hey Azirella")
- Voice requires HTTPS or localhost (Chrome restriction)
- Azirella panel is a right-side chat panel in WorkspaceShell (380px width)

### Sidebar
- `CapabilityAwareSidebar.jsx` — RBAC-filtered navigation, only visible in admin tabs
- `adminOnly` prop filters to Administration/AI/Deployment sections
- Click handler calls `useTabStore.openTab()` then `navigate()`

### Component Library
- Common components in `components/common/` (Button, Card, Badge, Input, etc.)
- `cn()` utility from `lib/utils/cn.js` for className merging
- Icons: always from `lucide-react`, never from Material UI

## Conventions
- No hardcoded data — all displayed data from DB or calculations
- No emojis in code unless user explicitly requests
- Use `cn()` for conditional classNames, not ternary string concatenation
- All API calls via `services/*.js` — never raw `fetch()` or `axios` in components
- Page components in `pages/`, reusable UI in `components/`
- Decision Stream components in `components/decision-stream/`

## Key Files
- `App.js` — ~120 route definitions, `RequireAuth` wrapper, `LayoutWrapper`
- `config/navigationConfig.js` — RBAC-filtered navigation items (~1100 lines)
- `contexts/AuthContext.js` — user auth state, `useAuth()` hook
- `contexts/ActiveConfigContext.js` — current supply chain config
- `services/api.js` — Axios instance, `api` and `simulationApi` exports

## Build & Deploy
```bash
docker compose build frontend    # Build the image
docker compose up -d frontend    # Deploy container
docker compose restart proxy     # Restart Nginx (picks up new build)
```
Frontend serves via Nginx on port 3000 inside Docker, proxied at `:8088`.

import { createTheme } from "@mui/material/styles";

const PRIMARY = "#2563EB";     // Brand blue
const PRIMARY_HOVER = "#1D4ED8";
const ACCENT = "#0EA5E9";
const BG_DEFAULT = "#F7F9FC";
const BG_PAPER = "#F0F4FF";
const FONT_STACK = "'Trebuchet MS', 'TrebuchetMS', 'Lucida Sans Unicode', 'Lucida Grande', sans-serif";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: PRIMARY, dark: PRIMARY_HOVER, contrastText: "#fff" },
    secondary: { main: ACCENT },
    background: { default: BG_DEFAULT, paper: BG_PAPER },
    text: { primary: "#0F172A", secondary: "#475569" },
    divider: "rgba(15, 23, 42, 0.08)",
  },
  typography: {
    fontFamily: FONT_STACK,
    // Figma-like type ramp (approximate)
    h1: { fontWeight: 700, fontSize: "2.5rem", letterSpacing: "-0.01em", lineHeight: 1.2 }, // 40px
    h2: { fontWeight: 700, fontSize: "2rem", lineHeight: 1.25 }, // 32px
    h3: { fontWeight: 600, fontSize: "1.5rem", lineHeight: 1.3 }, // 24px
    h4: { fontWeight: 600, fontSize: "1.25rem", lineHeight: 1.35 }, // 20px
    h5: { fontWeight: 600, fontSize: "1.125rem" }, // 18px
    h6: { fontWeight: 600, fontSize: "1rem" }, // 16px
    body1: { fontSize: "1rem", lineHeight: 1.6 },   // 16px
    body2: { fontSize: "0.875rem", lineHeight: 1.5 },// 14px
    subtitle1: { fontSize: "0.95rem", color: "#475569" },
    subtitle2: { fontSize: "0.8rem", color: "#64748B" },
    overline: { fontSize: "0.75rem", letterSpacing: ".06em", textTransform: "uppercase" },
    button: { fontWeight: 600, textTransform: "none", letterSpacing: 0 },
  },
  shape: { borderRadius: 16 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "html, body, #root": { height: "100%" },
        body: { backgroundColor: BG_DEFAULT, fontFamily: FONT_STACK },
        main: { backgroundColor: BG_DEFAULT },
      },
    },
    // Pill, shadowed "Contact Us" style buttons everywhere
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: 9999,
          paddingInline: 24,
          paddingBlock: 12,
          boxShadow:
            "0 1px 1px rgba(0,0,0,.04), 0 8px 16px -8px rgba(37,99,235,.35)",
        },
        containedPrimary: {
          ":hover": {
            backgroundColor: PRIMARY_HOVER,
            boxShadow:
              "0 1px 1px rgba(0,0,0,.04), 0 10px 18px -10px rgba(37,99,235,.45)",
          },
        },
      },
    },
    // Glassy top bar like Luma; we then pad pages to create the gap
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "rgba(255,255,255,0.8)",
          backdropFilter: "blur(8px)",
          color: "#0F172A",
          boxShadow: "inset 0 -1px 0 rgba(15,23,42,0.06)",
        },
      },
    },
    MuiToolbar: {
      styleOverrides: { root: { minHeight: 72 } },
    },
    // Soft card surface for shaded blocks / role selection
    MuiPaper: {
      defaultProps: { elevation: 0, variant: "outlined" },
      styleOverrides: {
        outlined: {
          background: BG_PAPER,
          borderColor: "rgba(30, 64, 175, 0.18)",
          boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          background: BG_PAPER,
          borderColor: "rgba(30, 64, 175, 0.18)",
          boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
        },
      },
    },
    MuiFormLabel: {
      styleOverrides: {
        root: {
          fontFamily: FONT_STACK,
          fontWeight: 600,
          fontSize: "1rem",
          color: "#0f172a",
        },
      },
    },
    MuiFormHelperText: {
      styleOverrides: {
        root: {
          fontFamily: FONT_STACK,
          fontSize: "0.75rem",
          color: "#4a5568",
        },
      },
    },
  },
});

export default theme;

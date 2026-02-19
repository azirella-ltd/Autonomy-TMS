import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2563EB',  // Brand blue
      light: '#60A5FA',  // Lighter blue
      dark: '#1D4ED8',  // Darker blue
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#5f6368',
      light: '#8e8e8e',
      dark: '#3c4043',
      contrastText: '#ffffff',
    },
    background: {
      default: '#f8f9fa',
      paper: '#ffffff',
    },
    text: {
      primary: '#202124',
      secondary: '#5f6368',
      disabled: 'rgba(0, 0, 0, 0.38)',
    },
    error: {
      main: '#d93025',
    },
    warning: {
      main: '#f9ab00',
    },
    info: {
      main: '#1a73e8',
    },
    success: {
      main: '#188038',
    },
    grey: {
      50: '#f8f9fa',
      100: '#f1f3f4',
      200: '#e8eaed',
      300: '#dadce0',
      400: '#bdc1c6',
      500: '#9aa0a6',
      600: '#5f6368',
      700: '#3c4043',
      800: '#202124',
      900: '#171717',
    },
  },
  typography: {
    fontFamily: '"Google Sans", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontSize: '2.25rem',
      fontWeight: 400,
      lineHeight: 1.2,
      margin: '1.5rem 0 1rem',
      color: '#202124',
    },
    h2: {
      fontSize: '1.75rem',
      fontWeight: 400,
      lineHeight: 1.2,
      margin: '1.25rem 0 0.75rem',
      color: '#202124',
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 500,
      lineHeight: 1.25,
      margin: '1rem 0 0.5rem',
      color: '#202124',
    },
    h4: {
      fontSize: '1.25rem',
      fontWeight: 500,
      lineHeight: 1.3,
      margin: '0.75rem 0',
      color: '#202124',
    },
    h5: {
      fontSize: '1.125rem',
      fontWeight: 500,
      lineHeight: 1.4,
      margin: '0.5rem 0',
      color: '#202124',
    },
    h6: {
      fontSize: '1rem',
      fontWeight: 500,
      lineHeight: 1.4,
      margin: '0.5rem 0',
      color: '#5f6368',
      textTransform: 'uppercase',
      letterSpacing: '0.025em',
    },
    body1: {
      fontSize: '1rem',
      lineHeight: 1.5,
      color: '#3c4043',
    },
    body2: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
      color: '#5f6368',
    },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#ffffff',
          color: '#5f6368',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#f8f9fa',
          borderRight: '1px solid #e0e0e0',
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: '0 20px 20px 0',
          margin: '0 8px',
          padding: '0 12px',
          '&.Mui-selected': {
            backgroundColor: '#EFF6FF',  // Light blue background
            color: '#2563EB',  // Brand blue
            '&:hover': {
              backgroundColor: '#EFF6FF',
            },
          },
          '&:hover': {
            backgroundColor: '#f1f3f4',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          boxShadow: '0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15)',
          transition: 'box-shadow 0.2s ease-in-out',
          '&:hover': {
            boxShadow: '0 1px 3px 0 rgba(60,64,67,0.3), 0 4px 8px 3px rgba(60,64,67,0.15)',
          },
        },
        outlined: {
          border: '1px solid #dadce0',
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 1px 3px 0 rgba(60,64,67,0.3)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 4,
          fontWeight: 500,
          padding: '8px 16px',
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 1px 2px 0 rgba(26,115,232,0.45), 0 1px 3px 1px rgba(26,115,232,0.3)',
          },
        },
        contained: {
          '&:hover': {
            boxShadow: '0 1px 2px 0 rgba(26,115,232,0.45), 0 1px 3px 1px rgba(26,115,232,0.3)',
          },
        },
        outlined: {
          border: '1px solid #dadce0',
          '&:hover': {
            backgroundColor: 'rgba(26, 115, 232, 0.04)',
            borderColor: '#d2e3fc',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: '1px solid #dadce0',
          boxShadow: '0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15)',
          '&:hover': {
            boxShadow: '0 1px 3px 0 rgba(60,64,67,0.3), 0 4px 8px 3px rgba(60,64,67,0.15)',
          },
        },
      },
    },
  },
});

export { theme };

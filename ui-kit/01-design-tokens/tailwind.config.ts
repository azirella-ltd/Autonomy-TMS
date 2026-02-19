import type { Config } from "tailwindcss";

/**
 * Autonomy Prototype - Tailwind Configuration
 *
 * This configuration defines the complete design system for the Autonomy.
 * It uses CSS custom properties (defined in globals.css) for theme values to enable runtime theme switching.
 *
 * Primary Brand Color: Emerald Green (HSL: 138 91% 26%)
 * - Conveys growth, trust, and forward momentum
 * - Used for primary actions, focus states, and primary content
 */

export default {
  // Enable class-based dark mode
  darkMode: ["class"],

  // Content paths - adjust these for your project structure
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],

  prefix: "",

  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px", // Maximum content width
      },
    },
    extend: {
      // Color System
      // All colors reference CSS variables for runtime theme switching
      colors: {
        // Base colors
        border: "var(--border)",           // Subtle borders (light gray)
        input: "var(--input)",             // Input field backgrounds
        ring: "var(--ring)",               // Focus ring color (emerald)
        background: "var(--background)",   // Page background (white/dark)
        foreground: "var(--foreground)",   // Primary text color

        // Primary brand color (emerald green)
        primary: {
          DEFAULT: "hsl(var(--primary))",           // Main emerald green
          hover: "hsl(var(--primary-hover))",       // Darker emerald for hover states
          foreground: "hsl(var(--primary-foreground))", // White text on primary
        },

        // Secondary/muted colors (grays)
        secondary: {
          DEFAULT: "var(--secondary)",               // Very light gray
          foreground: "var(--secondary-foreground)", // Dark text on secondary
        },

        // Status colors
        destructive: {
          DEFAULT: "var(--destructive)",               // Red for errors/destructive actions
          foreground: "var(--destructive-foreground)", // White text on destructive
        },
        warning: {
          DEFAULT: "var(--warning)",               // Amber/gold for warnings
          foreground: "var(--warning-foreground)", // Dark text on warning
        },
        info: {
          DEFAULT: "var(--info)",               // Blue for informational messages
          foreground: "var(--info-foreground)", // White text on info
        },

        // Muted/subtle colors
        muted: {
          DEFAULT: "var(--muted)",               // Light gray for disabled/subtle
          foreground: "var(--muted-foreground)", // Medium gray for secondary text
        },

        // Accent colors
        accent: {
          DEFAULT: "var(--accent)",               // Light accent background
          foreground: "var(--accent-foreground)", // Text on accent
        },

        // Popover/dropdown colors
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },

        // Card colors
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },

        // Sidebar-specific colors
        sidebar: {
          DEFAULT: "var(--sidebar-background)",
          foreground: "var(--sidebar-foreground)",
          active: "var(--sidebar-active)",                   // Active menu item background
          "active-foreground": "var(--sidebar-active-foreground)", // Active item text
          primary: "var(--sidebar-primary)",                 // Primary sidebar color (emerald)
          "primary-foreground": "var(--sidebar-primary-foreground)",
          accent: "var(--sidebar-accent)",
          "accent-foreground": "var(--sidebar-accent-foreground)",
          border: "var(--sidebar-border)",
          ring: "var(--sidebar-ring)",
        },
      },

      // Border Radius System
      // Consistent rounded corners throughout the app
      borderRadius: {
        lg: "var(--radius)",                    // 10px - Large components (cards, dialogs)
        md: "calc(var(--radius) - 2px)",        // 8px - Medium components
        sm: "calc(var(--radius) - 4px)",        // 6px - Small components (buttons)
      },

      // Keyframe Animations
      // Complex animations for interactive elements and transitions
      keyframes: {
        // Simple pop effect for step indicators
        "step-pop": {
          "0%": { transform: "scale(0.95)" },
          "50%": { transform: "scale(1.08)" },
          "100%": { transform: "scale(1)" },
        },

        // Accordion animations (Radix UI)
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },

        // Complex particle absorption animations (Agent Setup page)
        // These create a magnetic effect where particles organize then absorb into center
        "organize-then-absorb-1": {
          "0%": { transform: "translate(-65px, -55px) rotate(-8deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(0px, -52px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(0px, -26px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-2": {
          "0%": { transform: "translate(55px, -45px) rotate(12deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(36px, -36px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(18px, -18px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-3": {
          "0%": { transform: "translate(70px, 5px) rotate(-15deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(52px, 0px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(26px, 0px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-4": {
          "0%": { transform: "translate(60px, 55px) rotate(10deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(36px, 36px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(18px, 18px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-5": {
          "0%": { transform: "translate(-5px, 65px) rotate(-12deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(0px, 52px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(0px, 26px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-6": {
          "0%": { transform: "translate(-60px, 60px) rotate(14deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(-36px, 36px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(-18px, 18px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-7": {
          "0%": { transform: "translate(-70px, 0px) rotate(-18deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(-52px, 0px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(-26px, 0px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },
        "organize-then-absorb-8": {
          "0%": { transform: "translate(-55px, -50px) rotate(16deg) scale(1)", opacity: "0.6" },
          "40%": { transform: "translate(-36px, -36px) rotate(0deg) scale(1)", opacity: "0.8" },
          "70%": { transform: "translate(-18px, -18px) scale(0.5)", opacity: "0.4" },
          "100%": { transform: "translate(0px, 0px) scale(0)", opacity: "0" },
        },

        // Magnetic slide animations (particles sliding into lanes)
        "magnetic-slide-lane1": {
          "0%": { opacity: "0.5", transform: "translate(0, 0) scale(1) rotate(var(--tw-rotate))" },
          "30%": { opacity: "0.7", transform: "translate(40px, -25px) scale(0.9) rotate(0deg)" },
          "50%": { transform: "translate(80px, -35px) scale(0.7) rotate(0deg)" },
          "70%": { transform: "translate(120px, -45px) scale(0.5) rotate(0deg)", opacity: "0.5" },
          "85%": { transform: "translate(150px, -50px) scale(0.3) rotate(0deg)", opacity: "0.3" },
          "100%": { opacity: "0", transform: "translate(180px, -55px) scale(0.1) rotate(0deg)" },
        },
        "magnetic-slide-lane2": {
          "0%": { opacity: "0.5", transform: "translate(0, 0) scale(1) rotate(var(--tw-rotate))" },
          "30%": { opacity: "0.7", transform: "translate(50px, 0px) scale(0.9) rotate(0deg)" },
          "50%": { transform: "translate(90px, 0px) scale(0.7) rotate(0deg)" },
          "70%": { transform: "translate(130px, 0px) scale(0.5) rotate(0deg)", opacity: "0.5" },
          "85%": { transform: "translate(160px, 0px) scale(0.3) rotate(0deg)", opacity: "0.3" },
          "100%": { opacity: "0", transform: "translate(190px, 0px) scale(0.1) rotate(0deg)" },
        },
        "magnetic-slide-lane3": {
          "0%": { opacity: "0.5", transform: "translate(0, 0) scale(1) rotate(var(--tw-rotate))" },
          "30%": { opacity: "0.7", transform: "translate(45px, 25px) scale(0.9) rotate(0deg)" },
          "50%": { transform: "translate(85px, 35px) scale(0.7) rotate(0deg)" },
          "70%": { transform: "translate(125px, 45px) scale(0.5) rotate(0deg)", opacity: "0.5" },
          "85%": { transform: "translate(155px, 50px) scale(0.3) rotate(0deg)", opacity: "0.3" },
          "100%": { opacity: "0", transform: "translate(185px, 55px) scale(0.1) rotate(0deg)" },
        },

        // Spark draw animations (visual effects)
        "spark-draw-1": {
          "0%": { opacity: "0", transform: "translate(0, 0) scale(0.5)" },
          "20%": { opacity: "1", transform: "translate(20px, -6px) scale(1)" },
          "100%": { opacity: "0.8", transform: "translate(180px, -55px) scale(0.8)" },
        },
        "spark-draw-2": {
          "0%": { opacity: "0", transform: "translate(0, 0) scale(0.5)" },
          "20%": { opacity: "1", transform: "translate(20px, 0px) scale(1)" },
          "100%": { opacity: "0.8", transform: "translate(190px, 0px) scale(0.8)" },
        },
        "spark-draw-3": {
          "0%": { opacity: "0", transform: "translate(0, 0) scale(0.5)" },
          "20%": { opacity: "1", transform: "translate(20px, 6px) scale(1)" },
          "100%": { opacity: "0.8", transform: "translate(185px, 55px) scale(0.8)" },
        },

        // Lane drawing animation
        "lane-draw": {
          "0%": { opacity: "0", width: "0" },
          "30%": { opacity: "0.6" },
          "100%": { opacity: "0.4", width: "200px" },
        },

        // Logo animations
        "logo-reveal": {
          "0%": { opacity: "0" },
          "1%": { opacity: "1" },
          "100%": { opacity: "1" },
        },
        "logo-fill": {
          "0%": { height: "0%" },
          "100%": { height: "100%" },
        },

        // Ready state appearance
        "ready-appear": {
          "0%": { opacity: "0", transform: "translateX(-50%) translateY(48px) scale(0.5)" },
          "50%": { transform: "translateX(-50%) translateY(48px) scale(1.1)" },
          "100%": { opacity: "1", transform: "translateX(-50%) translateY(48px) scale(1)" },
        },

        // Simple fade in
        "text-appear": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },

        // Slide up entrance
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },

        // Scale in entrance
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },

      // Animation Utility Classes
      // Common animations ready to use with Tailwind classes
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "text-appear 0.3s ease-out",
        "slide-up": "slide-up 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
      },
    },
  },

  // Required plugin for animation utilities
  plugins: [require("tailwindcss-animate")],
} satisfies Config;

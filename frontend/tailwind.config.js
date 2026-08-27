/** @type {import('tailwindcss').Config} */

// Reads each color from a CSS custom property so the same utility classes
// (bg-brand-500, text-ink-900, border-line-200, bg-success/10, ...) resolve
// to different values under .dark without any changes at the call sites.
// Opacity modifiers (e.g. bg-brand-500/10) keep working because the
// variable holds an "R G B" triplet, not a full color string.
function withOpacity(variable) {
  return ({ opacityValue }) =>
    opacityValue === undefined ? `rgb(var(${variable}))` : `rgb(var(${variable}) / ${opacityValue})`;
}

export default {
  darkMode: ['class'],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Ingage LMS design-system tokens (brand green, ink, semantic states)
        brand: {
          50: withOpacity('--color-brand-50'),
          100: withOpacity('--color-brand-100'),
          500: withOpacity('--color-brand-500'),
          600: withOpacity('--color-brand-600'),
          700: withOpacity('--color-brand-700'),
          800: withOpacity('--color-brand-800'),
        },
        ink: {
          900: withOpacity('--color-ink-900'),
          700: withOpacity('--color-ink-700'),
          600: withOpacity('--color-ink-600'),
          500: withOpacity('--color-ink-500'),
          400: withOpacity('--color-ink-400'),
        },
        line: {
          100: withOpacity('--color-line-100'),
          200: withOpacity('--color-line-200'),
          300: withOpacity('--color-line-300'),
        },
        surface: withOpacity('--color-surface'),
        card: withOpacity('--color-card'),
        // Fixed, non-theme-flipping foreground for text/icons that sit on
        // the brand-500 fill itself (the button stays vivid green in both
        // themes, so its label must stay dark in both themes too).
        'on-brand': withOpacity('--color-on-brand'),
        success: {
          DEFAULT: withOpacity('--color-success'),
          bg: withOpacity('--color-success-bg'),
          line: withOpacity('--color-success-line'),
          solid: withOpacity('--color-success-solid'),
        },
        warning: {
          DEFAULT: withOpacity('--color-warning'),
          bg: withOpacity('--color-warning-bg'),
          line: withOpacity('--color-warning-line'),
          solid: withOpacity('--color-warning-solid'),
        },
        danger: {
          DEFAULT: withOpacity('--color-danger'),
          bg: withOpacity('--color-danger-bg'),
          line: withOpacity('--color-danger-line'),
          solid: withOpacity('--color-danger-solid'),
        },
        info: {
          DEFAULT: withOpacity('--color-info'),
          bg: withOpacity('--color-info-bg'),
          line: withOpacity('--color-info-line'),
          solid: withOpacity('--color-info-solid'),
        },
        accent: {
          DEFAULT: withOpacity('--color-accent'),
          bg: withOpacity('--color-accent-bg'),
          line: withOpacity('--color-accent-line'),
          solid: withOpacity('--color-accent-solid'),
        },
      },
      borderRadius: {
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        '2xl': '24px',
      },
      boxShadow: {
        card: '0 1px 3px rgba(52,51,53,.08), 0 1px 2px -1px rgba(52,51,53,.08)',
        popover: '0 10px 15px -3px rgba(52,51,53,.10), 0 4px 6px -4px rgba(52,51,53,.08)',
      },
    },
  },
  plugins: [],
}

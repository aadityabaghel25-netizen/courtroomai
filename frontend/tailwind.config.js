/** @type {import('tailwindcss').Config} */
// Light, high-contrast enterprise theme. The `ink` scale runs from the page
// background (950) to body text (100), so components read "ink-900 = surface,
// ink-100 = strongest text".
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['"Source Serif 4"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink: {
          950: '#f5f6f8',
          900: '#ffffff',
          850: '#fbfbfc',
          800: '#f0f2f5',
          700: '#e3e6eb',
          600: '#cdd2da',
          500: '#8a92a0',
          400: '#5f6775',
          300: '#454c59',
          200: '#2b313c',
          100: '#141821',
        },
        brand: {
          700: '#1b2a4a',
          600: '#24365e',
          500: '#2f4677',
          100: '#e8edf7',
        },
        bronze: {
          600: '#7a5523',
          500: '#8e652d',
          400: '#a87b3d',
          300: '#8e652d',
          200: '#7a5523',
        },
        verdict: {
          pass: '#047857',
          weak: '#b45309',
          fail: '#be123c',
          unknown: '#64748b',
        },
      },
      maxWidth: { doc: '720px', shell: '1240px' },
      letterSpacing: { label: '0.08em' },
      boxShadow: {
        glow: '0 0 0 2px rgba(47,70,119,0.25), 0 8px 24px -12px rgba(27,42,74,0.35)',
        card: '0 1px 2px rgba(20,24,33,0.05), 0 8px 24px -16px rgba(20,24,33,0.12)',
      },
      keyframes: {
        sweep: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(100%)' } },
      },
      animation: { sweep: 'sweep 1.6s ease-in-out infinite' },
    },
  },
  plugins: [],
}

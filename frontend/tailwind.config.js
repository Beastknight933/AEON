/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        aeon: {
          bg: '#090d16',
          card: '#0e1422',
          surface: '#141c2e',
          surfaceHover: '#1a243a',
          border: '#1e293b',
          borderSubtle: '#151d2d',
          accent: '#0070ba',
          cyan: '#38bdf8',
          textMuted: '#64748b',
          textSecondary: '#94a3b8',
          textPrimary: '#f8fafc',
          success: '#10b981',
          danger: '#ef4444',
          warning: '#f59e0b',
        }
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      }
    },
  },
  plugins: [],
}

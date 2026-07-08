import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#18212f',
        mist: '#edf4f2',
        trail: '#2f7d67',
        coral: '#e06a4f',
      },
      boxShadow: {
        panel: '0 16px 50px rgb(31 52 47 / 12%)',
      },
    },
  },
  plugins: [],
} satisfies Config;

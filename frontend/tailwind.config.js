export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#162033',
        ocean: '#116466',
        mint: '#47c4a6',
        coral: '#f9735b',
        amber: '#f8b84e'
      },
      animation: {
        blob: 'blob 8s ease-in-out infinite',
        float: 'float 6s ease-in-out infinite'
      },
      keyframes: {
        blob: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(24px, -18px) scale(1.05)' },
          '66%': { transform: 'translate(-16px, 12px) scale(0.96)' }
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' }
        }
      }
    }
  },
  plugins: []
}

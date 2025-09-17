/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        blue: {
          100: '#EBF8FF',
          500: '#4299E1',
          700: '#2B6CB0',
          800: '#2C5282',
        },
      },
    },
  },
  plugins: [],
}

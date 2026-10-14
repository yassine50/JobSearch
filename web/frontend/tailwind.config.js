
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        slate: {
          650: '#415067',
          750: '#293548',
          850: '#172033',
        }
      }
    }
  },
  plugins: [],
}

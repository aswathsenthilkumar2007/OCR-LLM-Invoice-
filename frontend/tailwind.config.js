/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111c34",
        canvas: "#f5f7fb",
        accent: "#3478f6",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 2px 8px rgba(20, 37, 66, 0.035), 0 1px 2px rgba(20, 37, 66, 0.025)",
        float: "0 20px 60px rgba(13, 27, 53, 0.18)",
      },
    },
  },
  plugins: [],
};

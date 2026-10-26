/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "../phase-12-research-ui/src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        trail: {
          50: "#f3f7f4",
          100: "#e2ebe4",
          200: "#c5d7ca",
          300: "#9bbba4",
          400: "#6f9a7c",
          500: "#4f7d5f",
          600: "#3c634a",
          700: "#314f3c",
          800: "#294032",
          900: "#22362a",
        },
        skyline: {
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
        },
        ember: {
          400: "#fbbf24",
          500: "#f59e0b",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "trail-light":
          "radial-gradient(ellipse at 20% 0%, rgba(79,125,95,0.12), transparent 50%), radial-gradient(ellipse at 90% 10%, rgba(14,165,233,0.1), transparent 45%), linear-gradient(180deg, #f3f7f4 0%, #e8f0ec 100%)",
        "trail-dark":
          "radial-gradient(ellipse at 15% 0%, rgba(79,125,95,0.25), transparent 45%), radial-gradient(ellipse at 85% 5%, rgba(14,165,233,0.15), transparent 40%), linear-gradient(180deg, #0f1612 0%, #152019 100%)",
      },
    },
  },
  plugins: [],
};

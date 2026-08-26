/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        panel: "#11161d",
        border: "#30363d",
        text: "#c9d1d9",
        muted: "#8b949e",
        green: "#2ea043",
        "green-dim": "#23863633",
        blue: "#58a6ff",
        purple: "#a371f7",
        orange: "#f0883e",
        red: "#f85149",
        yellow: "#e3b341",
      },
    },
  },
  plugins: [],
}

import type { Config } from "tailwindcss";
import { colors } from "./src/theme/colors";
import { fontFamily, fontSize } from "./src/theme/typography";
import { spacing } from "./src/theme/spacing";
import { borderRadius } from "./src/theme/radius";
import { boxShadow } from "./src/theme/shadow";
import { animation, keyframes } from "./src/theme/motion";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors,
      fontFamily,
      fontSize,
      spacing,
      borderRadius,
      boxShadow,
      keyframes,
      animation,
      // Customer Portal redesign — the Application Form's readable-width cap (~1200-1400px
      // asked for) — no custom maxWidth key existed before this.
      maxWidth: { app: "1320px" },
    },
  },
  plugins: [],
} satisfies Config;

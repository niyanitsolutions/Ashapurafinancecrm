// Enterprise redesign pass — subtle entrance/feedback animations (fade, slide, scale,
// shimmer for skeleton loading), consumed by tailwind.config.ts as `theme.extend.
// keyframes`/`animation`. Kept deliberately understated per the brief ("smooth, nothing
// flashy") — short durations, small distances, no bounce/spring easing.
export const keyframes = {
  fadeIn: {
    from: { opacity: "0" },
    to: { opacity: "1" },
  },
  slideUp: {
    from: { opacity: "0", transform: "translateY(10px)" },
    to: { opacity: "1", transform: "translateY(0)" },
  },
  scaleIn: {
    from: { opacity: "0", transform: "scale(0.96)" },
    to: { opacity: "1", transform: "scale(1)" },
  },
  shimmer: {
    "0%": { backgroundPosition: "-200% 0" },
    "100%": { backgroundPosition: "200% 0" },
  },
  countUp: {
    from: { opacity: "0.4", transform: "translateY(4px)" },
    to: { opacity: "1", transform: "translateY(0)" },
  },
} as const;

export const animation = {
  "fade-in": "fadeIn 0.35s ease-out both",
  "slide-up": "slideUp 0.35s ease-out both",
  "scale-in": "scaleIn 0.25s ease-out both",
  shimmer: "shimmer 1.6s linear infinite",
  "count-up": "countUp 0.3s ease-out both",
} as const;

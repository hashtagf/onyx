import type { IconProps } from "@opal/types";

// MSAI white-label wordmark. The original "onyx" glyphs were an SVG sized by
// a 64-unit-high viewBox; approximate the same visual height with text.
const SvgOnyxTyped = ({ size, className }: IconProps) => (
  <span
    className={className}
    style={{
      fontSize: size != null ? Number(size) * 0.62 : undefined,
      lineHeight: 1,
      fontWeight: 700,
      letterSpacing: "-0.02em",
      color: "var(--theme-primary-05)",
      userSelect: "none",
    }}
  >
    MSAI
  </span>
);
export default SvgOnyxTyped;

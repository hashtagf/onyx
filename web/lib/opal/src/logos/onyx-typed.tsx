import type { IconProps } from "@opal/types";

// SPIFFAI white-label wordmark. The original "onyx" glyphs were an SVG sized
// by a 64-unit-high viewBox; match that visual height with the SPIFF image.
const SvgOnyxTyped = ({ size, className, style }: IconProps) => (
  <img
    src="/logotype.png"
    alt="SPIFFAI"
    style={{
      height: size != null ? Number(size) * 0.62 : undefined,
      width: "auto",
      objectFit: "contain",
      flexShrink: 0,
      userSelect: "none",
      ...style,
    }}
    className={className}
  />
);
export default SvgOnyxTyped;

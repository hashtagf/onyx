import type { IconProps } from "@opal/types";

// SPIFFAI white-label: the SPIFF "S" mark. Orange gradient reads on both
// light and dark surfaces. Raster-based, so theme color vars do not apply.
const SvgOnyxLogo = ({ size, className }: IconProps) => (
  <img
    src="/logo.png"
    alt="SPIFFAI"
    width={size}
    height={size}
    style={{ objectFit: "contain", flexShrink: 0 }}
    className={className}
  />
);
export default SvgOnyxLogo;

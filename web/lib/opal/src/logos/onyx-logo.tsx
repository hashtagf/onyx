import type { IconProps } from "@opal/types";

// MSAI white-label: Maximum Soft hexagon mark. Blue on light backgrounds,
// white on dark. Raster-based, so theme color vars do not apply here.
const SvgOnyxLogo = ({ size, className }: IconProps) => (
  <>
    <img
      src="/logo-blue.png"
      alt="MSAI"
      width={size}
      height={size}
      style={{ objectFit: "contain", flexShrink: 0 }}
      className={"dark:hidden " + (className ?? "")}
    />
    <img
      src="/logo.png"
      alt="MSAI"
      width={size}
      height={size}
      style={{ objectFit: "contain", flexShrink: 0 }}
      className={"hidden dark:block " + (className ?? "")}
    />
  </>
);
export default SvgOnyxLogo;

import type { IconProps } from "@opal/types";
const SvgTelegramMono = ({ size, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 52 52"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    {...props}
  >
    <circle cx={26} cy={26} r={26} fill="#229ED9" />
    <path
      d="M12.78 24.93 40.1 13.5c.80-.31 1.56-.06 1.26 1.28L36.60 38.9c-.24 1.07-.94 1.33-1.91.83l-5.25-3.92-2.53 2.45c-.28.28-.52.52-1.06.52l1.65-7.28 7.07-6.4c.49-.44-.07-.5-.73-.03l-8.74 5.5-4.74-1.49c-1.05-.33-.12-.99.33-1.32l13.82-8.6c.71-.44-.12-.7-.85-.28L15.4 25.7c-1 .56-1.94.34-2.62-.77z"
      fill="#fff"
    />
  </svg>
);
export default SvgTelegramMono;

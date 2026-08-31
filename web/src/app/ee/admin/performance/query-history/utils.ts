import type { DateRange } from "@/refresh-components/DateRangePicker";
import {
  QUERY_HISTORY_PREVIEW_MAX_CHARS,
  START_QUERY_HISTORY_EXPORT_URL,
} from "./constants";

export function truncateQueryHistoryPreview(message: string): string {
  if (message.length <= QUERY_HISTORY_PREVIEW_MAX_CHARS) {
    return message;
  }

  return `${message.slice(0, QUERY_HISTORY_PREVIEW_MAX_CHARS - 1)}…`;
}

export const withRequestId = (url: string, requestId: string): string =>
  `${url}?request_id=${requestId}`;

export const withDateRange = (dateRange: DateRange): string => {
  if (!dateRange) {
    return START_QUERY_HISTORY_EXPORT_URL;
  }

  const { from, to } = dateRange;

  const fromString = from.toISOString();
  const toString = to.toISOString();

  return `${START_QUERY_HISTORY_EXPORT_URL}?start=${fromString}&end=${toString}`;
};

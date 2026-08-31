import { QUERY_HISTORY_PREVIEW_MAX_CHARS } from "@/app/ee/admin/performance/query-history/constants";
import { truncateQueryHistoryPreview } from "@/app/ee/admin/performance/query-history/utils";

describe("truncateQueryHistoryPreview", () => {
  it("keeps short messages unchanged", () => {
    expect(truncateQueryHistoryPreview("Short answer")).toBe("Short answer");
  });

  it("limits large messages before rendering them", () => {
    const preview = truncateQueryHistoryPreview(
      "a".repeat(QUERY_HISTORY_PREVIEW_MAX_CHARS + 100)
    );

    expect(preview).toHaveLength(QUERY_HISTORY_PREVIEW_MAX_CHARS);
    expect(preview.endsWith("…")).toBe(true);
  });
});

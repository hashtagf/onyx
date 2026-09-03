import { mergeFetchedModelConfigurations } from "@/sections/modals/languageModels/utils";
import type { ModelConfiguration } from "@/lib/languageModels/types";

function model(
  name: string,
  overrides: Partial<ModelConfiguration> = {}
): ModelConfiguration {
  return {
    name,
    is_visible: false,
    max_input_tokens: null,
    supports_image_input: false,
    supports_reasoning: false,
    effectiveDisplayName: name,
    ...overrides,
  };
}

describe("mergeFetchedModelConfigurations", () => {
  it("returns fetched models as-is when the form has no models", () => {
    const fetched = [model("a", { is_visible: true })];
    expect(mergeFetchedModelConfigurations(fetched, [])).toEqual(fetched);
  });

  it("keeps prior visibility and adds new models unselected", () => {
    const result = mergeFetchedModelConfigurations(
      [model("a"), model("b", { is_visible: true })],
      [model("a", { is_visible: true })]
    );
    expect(result.map((m) => [m.name, m.is_visible])).toEqual([
      ["a", true],
      ["b", false],
    ]);
  });

  it("keeps a prior vision flag when the gateway reports none", () => {
    const result = mergeFetchedModelConfigurations(
      [model("a"), model("b", { supports_image_input: true })],
      [model("a", { supports_image_input: true }), model("b")]
    );
    expect(result.map((m) => m.supports_image_input)).toEqual([true, true]);
  });
});

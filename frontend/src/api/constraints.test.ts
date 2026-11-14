import { expect, test } from "vitest";

import openapi from "../../openapi.json";
import { TAGS_MAX_ITEMS, TAG_MAX_LENGTH, TAG_PATTERN } from "./constraints";

test("constraints match openapi.json", () => {
  const { Tag, Tags } = openapi.components.schemas;

  expect(TAG_PATTERN).toBe(Tag.pattern);
  expect(TAG_MAX_LENGTH).toBe(Tag.maxLength);
  expect(TAGS_MAX_ITEMS).toBe(Tags.maxItems);
});

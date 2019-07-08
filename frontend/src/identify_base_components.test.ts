import { pathToComponentName } from "./identify_base_components";

describe("pathToComponentName", () => {
  it("takes the filename from a full path", () => {
    expect(pathToComponentName("./foo/bar/SomeComponent.vue")).toEqual(
      "SomeComponent"
    );
  });
  it("accepts just a filename with no preceding directories", () => {
    expect(pathToComponentName("SomeComponent.vue")).toEqual("SomeComponent");
  });
});

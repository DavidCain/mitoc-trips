import moment from "moment";

import { formatDate } from "./filters";

describe("formatDate", () => {
  it("returns null when passed null", function() {
    expect(formatDate(null)).toBe(null);
  });

  it("formats full moments", function() {
    const formatted = formatDate(moment("2019-07-01T12:29:27-05:00"));
    expect(formatted).toEqual("Jul 1, 2019"); // NOTE: uses client's timezone by default.
  });

  it("accepts custom format strings", function() {
    const formatString = "MMMM Do YYYY";
    const formatted = formatDate(
      moment("2019-07-01T12:29:27-05:00"),
      formatString
    );
    expect(formatted).toEqual("July 1st 2019"); // NOTE: uses client's timezone by default!
  });
});

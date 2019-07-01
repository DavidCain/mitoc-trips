import moment from "moment-timezone";
import { localize } from "./dateutil";

describe("localize", () => {
  function expectTranslation(input: string, output: string) {
    const localized = localize(moment(input));
    expect(localized.isSame(moment(output)));
  }

  it("handles when the first day of the month is a Sunday", () => {
    expectTranslation("1992-11-01T01:59:59", "1992-11-01T01:59:59-05:00");
  });

  it("handles right before DST switchover", () => {
    expectTranslation("2019-03-10T01:59:59", "2019-03-10T01:59:59-05:00");
  });

  it("handles right after DST switchover", () => {
    expectTranslation("2019-03-10T03:00:01", "2019-03-10T03:00:01-04:00");
  });

  // Sanity check our hackish method by comparing its output to moment-timezone on key datetimes
  // moment-timezone is not a production dependency, but it is a dev dependency
  describe("moment-timezone parity", () => {
    function expectMomentTimezoneParity(datetime: string) {
      const localized = localize(moment(datetime));
      const canonical = moment.tz(datetime, "America/New_York");
      // We cannot simply test that they are the same moment in time.
      // Rather, we need to test that they're annotated with the right UTC offsets
      expect(localized.format()).toEqual(canonical.format());
    }

    it("handles dates during DST", () => {
      expectMomentTimezoneParity("2019-04-15T12:34:59");
      expectMomentTimezoneParity("2019-05-01T00:00:00");
      expectMomentTimezoneParity("2019-06-30T23:59:59");
    });

    it("handles dates outside of DST", () => {
      expectMomentTimezoneParity("2018-12-31T23:59:59");
      expectMomentTimezoneParity("2019-01-01T00:00:00");
      expectMomentTimezoneParity("2019-01-01T12:34:59");
      expectMomentTimezoneParity("2019-12-01T00:00:00");
    });

    it("handles before and after DST switchover", () => {
      expectMomentTimezoneParity("2019-03-10T01:59:59");
      expectMomentTimezoneParity("2019-03-10T03:00:01");
    });

    it("handles before and after the return to standard time", () => {
      // Before and after fall return to standard time
      expectMomentTimezoneParity("2019-11-03T00:59:59");
      // expectMomentTimezoneParity("2019-11-03T01:59:59"); // Ambiguous - before DST switch? After? Who cares.
      expectMomentTimezoneParity("2019-11-03T02:00:01");
      expectMomentTimezoneParity("2019-12-03T03:00:01");
    });
  });
});

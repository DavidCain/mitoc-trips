import { setTimeTo } from "@/tests/util";
import {
  earlyRenewalAllowed,
  expirationIfRenewingToday,
  expiringSoon,
  statusIsActive,
} from "./status";
import moment from "moment";

let dateNowSpy: jest.SpyInstance;

describe("expiringSoon", () => {
  // Mock each test as if it's noon-ish in Boston on Jan 30, 2019
  // (Timezone effects shouldn't matter much in this test)
  beforeAll(() => {
    dateNowSpy = setTimeTo("2019-01-30T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  it("does not regard already-expired (past date) memberships as 'expiring soon'", () => {
    const yesterday = moment("2019-01-29");
    expect(expiringSoon(yesterday)).toBe(false);

    const lastYear = moment("2018-11-22");
    expect(expiringSoon(lastYear)).toBe(false);
  });

  it("does not regard memberships expiring today as 'expiring soon'", () => {
    const today = moment("2019-01-30");
    expect(expiringSoon(today)).toBe(false);
  });

  it("does not regard distant expirations as 'expiring soon'", () => {
    const twoMonthsLater = moment("2019-03-30");
    expect(expiringSoon(twoMonthsLater)).toBe(false);
  });

  it("properly handles a membership expiring soon", () => {
    const nextMonth = moment("2019-02-21");
    expect(expiringSoon(nextMonth)).toBe(true);
    const tomorrow = moment("2019-01-31");
    expect(expiringSoon(tomorrow)).toBe(true);
  });
});

describe("earlyRenewalAllowed & expirationIfRenewingToday", () => {
  let dateNowSpy: jest.SpyInstance;
  // Express now & one year later in different timezones to demonstrate tz math
  const now = moment("2025-09-30T12:34:56-05:00");
  const oneYearFromToday = moment("2026-09-30T11:34:56-06:00");

  beforeAll(() => {
    dateNowSpy = setTimeTo("2025-09-30T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  it("states one year from today if given no expiration date", () => {
    expect(earlyRenewalAllowed(null)).toBe(false);
    expect(expirationIfRenewingToday(null).isSame(oneYearFromToday)).toBe(true);
  });

  it("includes the remaining time on the membership if expiring soon", () => {
    // The membership expires in a little over two weeks!
    const expiresOn = moment("2025-10-15T12:34:56-05:00");
    const extraTime = moment("2026-10-15T11:34:56-06:00");
    expect(expiringSoon(expiresOn)).toBe(true);
    expect(earlyRenewalAllowed(expiresOn)).toBe(true);

    expect(expirationIfRenewingToday(expiresOn).isSame(extraTime)).toBe(true);
  });

  it("states one year from today if not expiring soon", () => {
    const exp = moment(now).add(2, "months");
    expect(expiringSoon(exp)).toBe(false);
    expect(earlyRenewalAllowed(exp)).toBe(false);

    expect(expirationIfRenewingToday(exp).isSame(oneYearFromToday)).toBe(true);
  });
});

describe("statusIsActive", () => {
  it("considers both Active and the special 'Expiring Soon' status active", () => {
    expect(statusIsActive("Active")).toBe(true);
    expect(statusIsActive("Expiring Soon")).toBe(true);
  });

  it("does not consider other statuses as active", () => {
    expect(statusIsActive("Expired")).toBe(false);
    expect(statusIsActive("Missing")).toBe(false);
    expect(statusIsActive("Missing Waiver")).toBe(false);
  });
});

import moment from "moment";

import { setTimeTo } from "./util";

it("Allows setting the current time", () => {
  // First, test that it's definitely not currently in the 1990's
  const datestring = "1990-12-30T12:34:56-05:00";
  expect(moment().isSame(moment(datestring))).toBe(false);

  // While our mock is active, successive calls all return the same moment!
  const dateNowSpy = setTimeTo(datestring);
  expect(moment().isSame(moment(datestring))).toBe(true);
  expect(moment().isSame(moment(datestring))).toBe(true);

  // We can eliminate our mock, and observe that date formatting works again
  dateNowSpy.mockRestore();
  expect(moment().isSame(moment(datestring))).toBe(false);
});

import axios from "axios";
import MockAdapter from "axios-mock-adapter";
import moment from "moment";

import { getMemberStatus, MembershipData, MembershipResponse } from "./actions";

describe("getMemberStatus", () => {
  let mockAxios: MockAdapter;

  beforeEach(() => {
    mockAxios = new MockAdapter(axios);
  });

  it("fetches information for the user", async () => {
    const rawResp: MembershipResponse = {
      membership: {
        expires: "2019-03-08",
        active: false,
        email: "mitoc.member@example.com",
      },
      waiver: { expires: "2020-02-02", active: true },
      status: "Missing Membership",
    };
    mockAxios.onGet("/users/37/membership.json").replyOnce((config) => {
      return [200, rawResp];
    });

    const data = await getMemberStatus(37);

    // It takes the raw date strings and coerces them to timezone-aware moments
    const memExpires = data.membership && data.membership.expires;
    const waiverExpires = data.waiver && data.waiver.expires;
    expect(
      memExpires && moment("2019-03-08T00:00:00-05:00").isSame(memExpires)
    ).toBe(true);
    expect(
      waiverExpires && moment("2020-02-02T00:00:00-05:00").isSame(waiverExpires)
    ).toBe(true);

    // Expect the full JSON response to be transformed to a typed object
    const expectedData: MembershipData = {
      membership: {
        email: "mitoc.member@example.com",
        active: false,
        // (We compared earlier, just re-use the actual object)
        expires: memExpires,
      },
      waiver: {
        active: true,
        // (We compared earlier, just re-use the actual object)
        expires: waiverExpires,
      },
      // Renamed from the keyword `status`
      membershipStatus: "Missing Membership",
    };
    expect(data).toEqual(expectedData);
  });

  it("handles users with null membership/waiver", async () => {
    const rawResp: MembershipResponse = {
      membership: {
        expires: null,
        active: false,
        email: "mitoc.member@example.com",
      },
      waiver: { expires: null, active: false },
      status: "Missing",
    };
    mockAxios.onGet("/users/42/membership.json").replyOnce((config) => {
      return [200, rawResp];
    });

    const data = await getMemberStatus(42);

    // Expect the full JSON response to be transformed to a typed object
    const expectedData: MembershipData = {
      membership: {
        email: "mitoc.member@example.com",
        active: false,
        expires: null,
      },
      waiver: {
        active: false,
        expires: null,
      },
      // Renamed from the keyword `status`
      membershipStatus: "Missing",
    };
    expect(data).toEqual(expectedData);
  });
});

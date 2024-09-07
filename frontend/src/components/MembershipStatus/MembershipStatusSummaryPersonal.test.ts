import Vue from "vue";
import moment, { Moment } from "moment";
import { shallowMount, Wrapper } from "@vue/test-utils";

import { setTimeTo } from "@/tests/util";

import { MembershipData } from "@/modules/membership/actions";
import { MembershipStatus } from "@/modules/membership/status";
import { localize } from "@/modules/dateutil";

import MembershipStatusSummaryPersonal from "./MembershipStatusSummaryPersonal.vue";

// TODO: Use the TypeScript counterpart for expect.extend to make a custom matcher
function strippedText(wrapper: Wrapper<Vue>) {
  return wrapper.text().replace(/\s+/g, " ");
}

function makeDate(date: string): Moment {
  return localize(moment(date));
}

const ACTIVE_MEMBERSHIP = {
  expires: makeDate("1999-01-23"),
  active: true,
  email: "bob@example.com",
};

const ACTIVE_WAIVER = { expires: makeDate("1999-01-19"), active: true };

describe("current membership - 'Active' and 'Expiring Soon'", () => {
  let dateNowSpy: jest.SpyInstance;

  beforeAll(() => {
    dateNowSpy = setTimeTo("2025-09-30T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  it("displays membership & waiver expiration when active", () => {
    const wrapper = shallowMount(MembershipStatusSummaryPersonal, {
      propsData: {
        data: {
          membership: ACTIVE_MEMBERSHIP,
          waiver: ACTIVE_WAIVER,
          membershipStatus: "Active",
        },
      },
    });
    const paragraphs = wrapper.findAll("p");
    expect(strippedText(paragraphs.at(0))).toEqual(
      "Your account is active! Dues are valid through Jan 23, 1999."
    );
    expect(paragraphs.at(1).text()).toEqual(
      "Your waiver will expire on Jan 19, 1999."
    );
  });

  it("prompts users to renew soon if their membership is nearing its end", () => {
    const wrapper = shallowMount(MembershipStatusSummaryPersonal, {
      propsData: {
        data: {
          membership: {
            expires: makeDate("2025-10-02"),
            active: true,
            email: "bob@example.com",
          },
          waiver: {
            expires: makeDate("2025-10-02"),
            active: true,
          },
          membershipStatus: "Expiring Soon",
        },
      },
    });

    expect(strippedText(wrapper)).toContain(
      "Annual dues expire soon! Renew today to keep your account valid until Oct 2, 2026."
    );
  });
});

describe("bad membership - 'Expired,' 'Missing,' and 'Missing Dues'", () => {
  it("tells the user if we've never received a dues payment", () => {
    const wrapper = shallowMount(MembershipStatusSummaryPersonal, {
      propsData: {
        data: {
          membership: { email: null, expires: null, active: false },
          waiver: { expires: null, active: false },
          membershipStatus: "Missing",
        },
      },
    });
    expect(strippedText(wrapper)).toEqual(
      "We have no information on file for any of your verified email addresses. " +
        "You must pay annual dues and sign a waiver in order to participate on trips, rent gear, or use cabins."
    );
    expect(wrapper.html()).toContain('href="/profile/membership/"');
    expect(wrapper.html()).toContain('href="/profile/waiver/"');
  });
});

describe("bad waiver - 'Missing Waiver' and 'Waiver Expired'", () => {
  it("prompts members (even with current dues) without a waiver to sign one", () => {
    const wrapper = shallowMount(MembershipStatusSummaryPersonal, {
      propsData: {
        data: {
          membership: ACTIVE_MEMBERSHIP,
          waiver: { expires: null, active: false },
          membershipStatus: "Missing Waiver",
        },
      },
    });
    expect(wrapper.text()).toEqual("Please sign a waiver.");
    expect(wrapper.html()).toContain('href="/profile/waiver/"');
  });

  it("prompts members with an expired waiver to sign one", () => {
    const wrapper = shallowMount(MembershipStatusSummaryPersonal, {
      propsData: {
        data: {
          membership: ACTIVE_MEMBERSHIP,
          waiver: { expires: makeDate("1982-11-12"), active: false },
          membershipStatus: "Waiver Expired",
        },
      },
    });
    expect(wrapper.text()).toEqual("Please sign a new waiver.");
    expect(wrapper.html()).toContain('href="/profile/waiver/"');
  });
});

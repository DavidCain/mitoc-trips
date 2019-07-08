import Vue from "vue";
import axios from "axios";
import MockAdapter from "axios-mock-adapter";

import { shallowMount, Wrapper } from "@vue/test-utils";

import { flushPromises, setTimeTo } from "@/tests/util";
import { MembershipResponse } from "@/modules/membership/actions";
import MembershipStatus from "./MembershipStatus.vue";
import MembershipStatusIndicator from "./MembershipStatus/MembershipStatusIndicator.vue";
import MembershipStatusSummaryPersonal from "./MembershipStatus/MembershipStatusSummaryPersonal.vue";

const ROUTE_REGEX = /\/users\/\d+\/membership.json/;
const MEMBERSHIP_RESPONSE: MembershipResponse = {
  membership: {
    expires: "2019-03-08",
    active: false,
    email: "foo@example.com"
  },
  waiver: { expires: "2020-02-02", active: true },
  status: "Missing Membership"
};
let mockAxios: MockAdapter;

/**
 * Shorthand for expecting a one-time 200 response.
 */
function respondsWith(resp: MembershipResponse): void {
  mockAxios.onGet(ROUTE_REGEX).replyOnce(config => {
    return [200, resp];
  });
}

function render(props?: Object): Wrapper<Vue> {
  return shallowMount(MembershipStatus, {
    propsData: { userId: 42, ...props }
  });
}

beforeEach(() => {
  mockAxios = new MockAdapter(axios);
});

describe("userId", () => {
  it("Queries membership data for the passed user", async () => {
    respondsWith(MEMBERSHIP_RESPONSE);
    const wrapper = render({ userId: 42 });
    await flushPromises();
    const singleGetRequest = mockAxios.history.get[0];
    expect(singleGetRequest.url).toEqual("/users/42/membership.json");
  });
});

it("Displays 'querying MITOC servers' while waiting for query to complete", async () => {
  respondsWith(MEMBERSHIP_RESPONSE);
  const wrapper = render();

  const queryingMsg = "Querying MITOC servers for membership status...";
  expect(wrapper.text()).toContain(queryingMsg);
  await flushPromises();
  expect(wrapper.text()).not.toContain(queryingMsg);
});

describe("Expiring Soon", () => {
  let dateNowSpy: jest.SpyInstance;

  beforeAll(() => {
    dateNowSpy = setTimeTo("2019-02-22T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  it("Applies a special status for active memberships soon expiring", async () => {
    const wrapper = render();

    respondsWith({
      membership: {
        // Active, but expiring in a couple days!
        expires: "2019-02-25",
        active: true,
        email: "foo@example.com"
      },
      waiver: { expires: "2010-03-01", active: true },
      status: "Active"
    });
    await flushPromises();
    const statusIndicator = wrapper.find(MembershipStatusIndicator);
    expect(statusIndicator.props("membershipStatus")).toEqual("Expiring Soon");
  });

  it("Leaves memberships with plenty of time remaining as 'Active'", async () => {
    const wrapper = render();

    respondsWith({
      membership: {
        // Active, plenty of time left
        expires: "2019-04-01",
        active: true,
        email: "foo@example.com"
      },
      waiver: { expires: "2010-03-01", active: true },
      status: "Active"
    });
    await flushPromises();
    const statusIndicator = wrapper.find(MembershipStatusIndicator);
    expect(statusIndicator.props("membershipStatus")).toEqual("Active");
  });
});

describe("Personalized or not", () => {
  beforeEach(() => {
    respondsWith(MEMBERSHIP_RESPONSE);
  });

  function hasSummary(wrapper: Wrapper<Vue>, present: boolean): void {
    const personalSummary = wrapper.find(MembershipStatusSummaryPersonal);
    expect(personalSummary.exists()).toBe(present);
  }

  it("Renders a third-party (not personalized) summary by default", async () => {
    const wrapper = render();
    await flushPromises();
    hasSummary(wrapper, false);
  });

  it("Renders a personalized summary when requested", async () => {
    const wrapper = render({ personalized: true });
    // Does not appear initially, since we have no data
    hasSummary(wrapper, false);
    await flushPromises();
    hasSummary(wrapper, true);
  });
});

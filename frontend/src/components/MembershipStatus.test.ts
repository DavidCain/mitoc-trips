import Vue from "vue";
import axios from "axios";
import MockAdapter from "axios-mock-adapter";

import { shallowMount, Wrapper } from "@vue/test-utils";

import { flushPromises, setTimeTo } from "@/tests/util";
import { MembershipResponse } from "@/modules/membership/actions";
import MembershipStatus from "./MembershipStatus.vue";
import MembershipStatusIndicator from "./MembershipStatus/MembershipStatusIndicator.vue";
import MembershipStatusFaq from "./MembershipStatus/MembershipStatusFaq.vue";
import MembershipStatusSummaryPersonal from "./MembershipStatus/MembershipStatusSummaryPersonal.vue";

const ROUTE_REGEX = /\/users\/\d+\/membership.json/;
const MEMBERSHIP_RESPONSE: MembershipResponse = {
  membership: {
    expires: "2019-03-08",
    active: false,
    email: "foo@example.com",
  },
  waiver: { expires: "2020-02-02", active: true },
  status: "Missing Dues",
};
let mockAxios: MockAdapter;

/**
 * Shorthand for expecting a one-time 200 response.
 */
function respondsWith(resp: MembershipResponse): void {
  mockAxios.onGet(ROUTE_REGEX).replyOnce((config) => {
    return [200, resp];
  });
}

function render(props?: Object): Wrapper<Vue> {
  return shallowMount(MembershipStatus, {
    propsData: { userId: 42, ...props },
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

describe("loadingMsg", () => {
  beforeEach(() => {
    respondsWith(MEMBERSHIP_RESPONSE);
  });

  it("Displays 'querying MITOC servers' on normal queries", async () => {
    const wrapper = render();

    const queryingMsg = "Querying MITOC servers for membership status...";
    expect(wrapper.text()).toContain(queryingMsg);
    await flushPromises();
    expect(wrapper.text()).not.toContain(queryingMsg);
  });

  it("Displays a 'processing' message if we just signed", async () => {
    const wrapper = render({ justSigned: true });

    const queryingMsg = "We're currently processing your waiver...";
    expect(wrapper.text()).toContain(queryingMsg);
    await flushPromises();
  });
});

describe("Expiring Soon", () => {
  let dateNowSpy: jest.SpyInstance;

  beforeAll(() => {
    dateNowSpy = setTimeTo("2019-02-22T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  it("Applies a special status for active dues soon expiring", async () => {
    respondsWith({
      membership: {
        // Active, but expiring in a couple days!
        expires: "2019-02-25",
        active: true,
        email: "foo@example.com",
      },
      waiver: { expires: "2010-03-01", active: true },
      status: "Active",
    });
    const wrapper = render();
    await flushPromises();

    const statusIndicator = wrapper.find(MembershipStatusIndicator);
    expect(statusIndicator.props("membershipStatus")).toEqual("Expiring Soon");
  });

  it("Leaves dues with plenty of time remaining as 'Active'", async () => {
    respondsWith({
      membership: {
        // Active, plenty of time left
        expires: "2019-04-01",
        active: true,
        email: "foo@example.com",
      },
      waiver: { expires: "2010-03-01", active: true },
      status: "Active",
    });
    const wrapper = render();
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

describe("FAQ", () => {
  function hasFaq(wrapper: Wrapper<Vue>, present: boolean): void {
    expect(wrapper.find(MembershipStatusFaq).exists()).toBe(present);
  }

  it("Does not render the FAQ by default", async () => {
    respondsWith(MEMBERSHIP_RESPONSE);
    const wrapper = render();
    await flushPromises();
    hasFaq(wrapper, false);
  });

  it("Renders a membership FAQ when requested", async () => {
    respondsWith({
      membership: {
        active: false,
        expires: "1963-12-28",
        email: "member.email@example.com",
      },
      waiver: {
        active: false,
        expires: "1963-12-28",
      },
      status: "Expired",
    });
    const wrapper = render({ showFullFaq: true });

    // Does not appear initially, since we have no data about the membership
    hasFaq(wrapper, false);
    await flushPromises();
    hasFaq(wrapper, true);

    const faq = wrapper.find(MembershipStatusFaq);
    expect(faq.props()).toEqual({
      membershipStatus: "Expired",
      email: "member.email@example.com",
    });
  });
});

describe("justSigned", () => {
  let dateNowSpy: jest.SpyInstance;

  beforeAll(() => {
    dateNowSpy = setTimeTo("2019-02-22T12:34:56-05:00");
  });

  afterAll(() => {
    dateNowSpy.mockRestore();
  });

  // TODO: Resolve the conflict of flushing & using fake timers
  // beforeEach(() => {
  //   jest.useFakeTimers();
  // });

  describe("true", () => {
    it("does not poll repeatedly if the first status returned is current", () => {
      respondsWith({
        ...MEMBERSHIP_RESPONSE,
        // This date is exactly one year in the future, which appears active!
        waiver: { active: true, expires: "2020-02-22" },
        status: "Active",
      });

      const wrapper = render({ justSigned: true });
      flushPromises();
    });

    // TODO: I plan to use jest.useFakeTimers, which currently mocks `setTimeout`
    // Unfortunately, that alters the behavior of `flushPromises()`.
    // There are multiple ways this can be resolved, though I can finish at another time.
    it("Polls at increasing intervals until a new waiver is given", () => {});

    it("Ceases polling after a fixed number of requests", () => {});
  });

  describe("false", () => {
    it("only makes one API request, regardless of status", () => {});
  });
});

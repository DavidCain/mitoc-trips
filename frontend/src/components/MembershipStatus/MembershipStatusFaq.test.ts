import { shallowMount } from "@vue/test-utils";
import MembershipStatusFaq from "./MembershipStatusFaq.vue";

describe("active statuses", () => {
  it("displays nothing if active", () => {
    const wrapper = shallowMount(MembershipStatusFaq, {
      propsData: { membershipStatus: "Active" }
    });
    expect(wrapper.text()).toEqual("");
  });

  it("displays nothing if expiring soon (since it is still active)", () => {
    const wrapper = shallowMount(MembershipStatusFaq, {
      propsData: { membershipStatus: "Expiring Soon" }
    });
    expect(wrapper.text()).toEqual("");
  });
});

describe("inactive statuses", () => {
  it("handles missing or expired memberships", () => {
    const wrapper = shallowMount(MembershipStatusFaq, {
      propsData: { membershipStatus: "Missing" }
    });
    expect(wrapper.text()).toContain("Why isn't my membership showing up?");
    expect(wrapper.text()).toContain("But I'm positive");
  });

  it("handles missing or expired waivers", () => {
    const wrapper = shallowMount(MembershipStatusFaq, {
      propsData: {
        membershipStatus: "Missing Waiver",
        email: "joe@example.com"
      }
    });
    expect(wrapper.text()).toContain("Why isn't my waiver showing up?");
    expect(wrapper.html()).toContain('<a href="/profile/waiver/"');
    expect(wrapper.text()).toContain("But I'm positive");
  });
});

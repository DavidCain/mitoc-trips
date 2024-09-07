import { shallowMount } from "@vue/test-utils";
import MembershipStatusIndicator from "./MembershipStatusIndicator.vue";
import { MembershipStatus } from "@/modules/membership/status";

it("renders the active state", () => {
  const wrapper = shallowMount(MembershipStatusIndicator, {
    propsData: { membershipStatus: "Active" },
  });
  expect(wrapper.text()).toEqual("Active");
  expect(wrapper.classes()).toEqual(["label", "label-success"]);
});

it("renders warning statuses", () => {
  const warningStatuses = ["Waiver Expired", "Missing Waiver", "Missing Dues"];
  warningStatuses.forEach((membershipStatus) => {
    const wrapper = shallowMount(MembershipStatusIndicator, {
      propsData: { membershipStatus },
    });
    expect(wrapper.text()).toEqual(membershipStatus);
    expect(wrapper.classes()).toEqual(["label", "label-warning"]);
  });
});

it("renders 'danger' statuses", () => {
  const warningStatuses = ["Expired", "Missing"];
  warningStatuses.forEach((membershipStatus) => {
    const wrapper = shallowMount(MembershipStatusIndicator, {
      propsData: { membershipStatus },
    });
    expect(wrapper.text()).toEqual(membershipStatus);
    expect(wrapper.classes()).toEqual(["label", "label-danger"]);
  });
});

it("renders the special 'expiring soon' status", () => {
  const wrapper = shallowMount(MembershipStatusIndicator, {
    propsData: { membershipStatus: "Expiring Soon" },
  });
  expect(wrapper.text()).toEqual("Expiring Soon");
  expect(wrapper.classes()).toEqual(["label", "label-info"]);
});

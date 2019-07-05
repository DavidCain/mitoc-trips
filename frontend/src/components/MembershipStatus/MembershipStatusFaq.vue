<template>
  <div v-if="!membershipIsActive">
    <div v-if="missingOrExpired" class="well">
      <h5>Why isn't my membership showing up?</h5>
      <p>
        We search for a current MITOC membership under any of your verified
        email addresses. If we find a matching membership, we tie that to your
        account.
      </p>

      <p>
        If you think you're a current member, but don't see yourself as active
        here, you've most likely signed up for a membership under another email
        address. Make sure that you add and verify any email address that you
        may have signed up with.
      </p>
    </div>

    <div v-if="waiverNotCurrent" class="well">
      <h5>Why isn't my waiver showing up?</h5>
      <p>
        First, ensure you
        <a href="/profile/waiver/">signed the waiver</a> under the same email
        address as your membership: {{ email }}
      </p>
    </div>

    <div class="well">
      <h5>
        But I'm positive that my account is under one of these email addresses!
      </h5>
      <p>
        If you've paid your membership dues, signed the waiver, and are still
        not seeing that you're an active member, please
        <a href="/contact/">contact us</a>.
      </p>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from "vue-property-decorator";
import { MembershipStatus, statusIsActive } from "@/modules/membership/status";

@Component
export default class MembershipStatusFaq extends Vue {
  @Prop() private membershipStatus!: MembershipStatus;
  @Prop() private email?: string;

  get membershipIsActive() {
    return statusIsActive(this.membershipStatus);
  }

  get missingOrExpired() {
    return (
      this.membershipStatus === "Missing" || this.membershipStatus === "Expired"
    );
  }

  get waiverNotCurrent() {
    return (
      this.membershipStatus === "Missing Waiver" ||
      this.membershipStatus === "Waiver Expired"
    );
  }
}
</script>

<template>
  <span class="label" v-bind:class="className" style="display: inline-block">
    {{ membershipStatus }}
  </span>
</template>

<script lang="ts">
import { Component, Prop, Vue } from "vue-property-decorator";
import { MembershipStatus } from "@/modules/membership/status";

// Map from each status type to a Bootstrap CSS class
const statusToBootstrapClass: Record<MembershipStatus, string> = {
  Active: "label-success",
  Expired: "label-danger",
  Missing: "label-danger",
  "Waiver Expired": "label-warning",
  "Missing Waiver": "label-warning",
  "Missing Dues": "label-warning",
  "Expiring Soon": "label-info", // Special front-end only status
};

@Component
export default class MembershipStatusIndicator extends Vue {
  @Prop() private membershipStatus!: MembershipStatus;

  get className(): string {
    return statusToBootstrapClass[this.membershipStatus];
  }
}
</script>

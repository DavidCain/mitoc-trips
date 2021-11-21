<template>
  <div>
    <p v-if="membershipStatus === 'Missing Waiver'">
      Please <a href="/profile/waiver/">sign a waiver</a>.
    </p>
    <p v-else-if="membershipStatus === 'Waiver Expired'">
      Please <a href="/profile/waiver/">sign a new waiver</a>.
    </p>
    <div v-else-if="membershipStatus === 'Expiring Soon'">
      <div class="alert alert-warning">
        <h4>Your membership is expiring soon!</h4>
        <p>
          <a href="/profile/membership/">Renew today</a>
          to keep your membership valid until
          {{ renewalValidUntil | formatDate }}.
        </p>
      </div>
      <p>
        Your waiver will expire on {{ data.waiver.expires | formatDate }}.
        <a href="/profile/waiver/">Sign another?</a>
      </p>
    </div>
    <div v-else-if="membershipStatus === 'Active'">
      <p>
        Your membership is active, and expires on
        {{ data.membership.expires | formatDate }}.
      </p>
      <p>Your waiver will expire on {{ data.waiver.expires | formatDate }}.</p>
    </div>
    <div v-else-if="membershipStatus === 'Missing Membership'">
      <p>We have a current waiver on file, but no active membership.</p>
      <p>
        You can still participate in mini-trips, but you'll need
        <a href="/profile/membership/">a full MITOC membership</a>
        in order to rent gear, use cabins, or join other trips.
      </p>
    </div>
    <div v-else-if="membershipStatus === 'Missing'">
      <p>
        We have no membership information on file for any of your
        <a href="/accounts/email/">verified email addresses.</a>
      </p>

      <p>
        You must <a href="/profile/membership/">become a member</a> and
        <a href="/profile/waiver/">sign a new waiver</a>
        in order to participate on trips, rent gear, or use cabins.
      </p>
    </div>
    <div v-else-if="membershipStatus === 'Expired'">
      <p>
        Your membership expired on {{ data.membership.expires | formatDate }}.
      </p>
      <p>
        Please <a href="/profile/membership/">renew your membership</a> and
        <a href="/profile/waiver/">sign a new waiver</a>.
      </p>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from "vue-property-decorator";

import moment, { Moment } from "moment";
import "@/filters";

import {
  MembershipStatus,
  expirationIfRenewingToday,
} from "@/modules/membership/status";
import { localize } from "@/modules/dateutil";
import { MembershipData } from "@/modules/membership/actions";

@Component
export default class MembershipStatusSummaryPersonal extends Vue {
  @Prop() private data!: MembershipData;

  get membershipStatus(): MembershipStatus {
    return this.data.membershipStatus;
  }

  get renewalValidUntil(): Moment {
    return expirationIfRenewingToday(this.data.membership.expires);
  }
}
</script>

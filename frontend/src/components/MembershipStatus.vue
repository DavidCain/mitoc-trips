<template>
  <div>
    <h3>
      Membership
      <MembershipStatusIndicator
        v-if="membershipData"
        v-bind:membershipStatus="membershipData.membershipStatus"
      ></MembershipStatusIndicator>
    </h3>

    <div v-if="membershipData">
      <MembershipStatusSummaryPersonal
        v-if="personalized"
        v-bind:data="membershipData"
      >
      </MembershipStatusSummaryPersonal>
      <MembershipStatusFaq
        v-if="showFullFaq && membershipData"
        v-bind:membershipStatus="membershipData.membershipStatus"
        v-bind:email="email"
      ></MembershipStatusFaq>
    </div>
    <div v-else>
      {{ loadingMsg }}
    </div>
  </div>
</template>

<script lang="ts">
import moment from "moment";
import { Component, Prop, Vue } from "vue-property-decorator";
import { getMemberStatus, MembershipData } from "@/modules/membership/actions";
import { expiringSoon } from "@/modules/membership/status";
import { localize } from "@/modules/dateutil";

import MembershipStatusIndicator from "./MembershipStatus/MembershipStatusIndicator.vue";
import MembershipStatusSummaryPersonal from "./MembershipStatus/MembershipStatusSummaryPersonal.vue";
import MembershipStatusFaq from "./MembershipStatus/MembershipStatusFaq.vue";

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

@Component({
  components: {
    MembershipStatusIndicator,
    MembershipStatusFaq,
    MembershipStatusSummaryPersonal
  }
})
export default class MembershipStatus extends Vue {
  @Prop() private userId!: number;
  @Prop() private personalized?: boolean;
  @Prop() private justSigned?: boolean;
  @Prop() private showFullFaq?: boolean;

  private membershipData: MembershipData | null = null;
  private queriesPerformed: number = 0;
  private maxQueries: number = 8;

  get email(): string | null {
    if (!this.membershipData) {
      return null;
    }

    return this.membershipData.membership.email;
  }

  get loadingMsg(): string | null {
    if (this.membershipData) {
      return null;
    } else if (this.justSigned) {
      return "We're currently processing your waiver...";
    } else {
      return "Querying MITOC servers for membership status...";
    }
  }

  /**
   * A new waiver can be regarded as processed if the current waiver is valid for a year.
   */
  private waiverUpdateReceived(data: MembershipData): boolean {
    if (!data.waiver.expires) {
      return false;
    }

    // If the waiver is expired, we can safely infer that no update was made, regardless of date
    if (!data.waiver.active) {
      return false;
    }

    // Otherwise, we have an active waiver on file! Make sure it's not stale.
    // If valid for one year, we can infer that it's recently signed (not an old waiver on file)
    const daysLeft = localize(data.waiver.expires).diff(moment(), "days");
    return daysLeft > 363; // Approximately one year - accounts for potential timezone errors
  }

  /**
   * Return true if we expect the back end to return a newer status on subsequent calls.
   *
   * In all other cases, return false.
   */
  private mustQueryAgain(data: MembershipData): boolean {
    // If the user hasn't recently signed a waiver, we assume the first status is accurate.
    if (!this.justSigned) {
      return false;
    }

    // If the current waiver is good for approximately one year, we needn't query again!
    if (this.waiverUpdateReceived(data)) {
      return false;
    }

    // Otherwise, query again until we've exhausted a sane number of retries
    return this.queriesPerformed < this.maxQueries;
  }

  /**
   * Poll as many times as needed (generally, just once) for the most current status.
   *
   * After signing a waiver, users are redirected to a page that load this component.
   * Post-completion, it takes a few seconds for DocuSign to register the completed waiver
   * then notify our backend of the completion (and for that backend to write to the database).
   *
   * Accordingly, upon this redirect we poll the backend repeatedly with the
   * assumption that we * will eventually get a waiver that expires in a year.
   */
  private async pollUntilWaiverAccurate(): Promise<MembershipData> {
    // Fetch current status - don't return just yet, as it may not yet be accurate
    let data = await getMemberStatus(this.userId);

    while (this.mustQueryAgain(data)) {
      this.queriesPerformed++;
      await sleep(500 * this.queriesPerformed);
      data = await getMemberStatus(this.userId);
    }
    return data;
  }

  async created() {
    this.membershipData = await this.pollUntilWaiverAccurate();

    const { expires } = this.membershipData.membership;

    // If the membership expires some time in the near future, create a special status
    // (Their membership is still active, but it is expiring soon)
    if (expires && expiringSoon(expires)) {
      this.membershipData.membershipStatus = "Expiring Soon";
    }
  }
}
</script>

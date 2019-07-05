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
      Querying MITOC servers for membership status...
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
  @Prop() private showFullFaq?: boolean;

  private membershipData: MembershipData | null = null;

  get email(): string | null {
    if (!this.membershipData) {
      return null;
    }

    return this.membershipData.membership.email;
  }

  async created() {
    this.membershipData = await getMemberStatus(this.userId);

    const { expires } = this.membershipData.membership;

    // If the membership expires some time in the near future, create a special status
    // (Their membership is still active, but it is expiring soon)
    if (expires && expiringSoon(expires)) {
      this.membershipData.membershipStatus = "Expiring Soon";
    }
  }
}
</script>

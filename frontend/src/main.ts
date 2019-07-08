import Vue from "vue";

import "./filters";
import MembershipStatus from "./components/MembershipStatus.vue";

Vue.config.productionTip = false;

new Vue({
  // TODO: https://vuejs.org/v2/guide/components-registration.html#Automatic-Global-Registration-of-Base-Components
  components: { MembershipStatus }
}).$mount("#root");

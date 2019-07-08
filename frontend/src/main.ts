import Vue from "vue";

import "./filters";
import registerBaseComponents from "./identify_base_components";

Vue.config.productionTip = false;
registerBaseComponents();

new Vue({}).$mount("#root");

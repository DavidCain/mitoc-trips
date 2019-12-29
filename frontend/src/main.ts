import Vue from "vue";

import "./filters";
import registerBaseComponents from "./identify_base_components";
import configureAxios from "./ajax";

Vue.config.productionTip = false;
configureAxios();
registerBaseComponents();

new Vue({}).$mount("#root");

<template>
  <!-- We use an anchor tag to make use of built-in Bootstrap styling -->
  <a href="#" v-on:click="postLogOut()"><slot></slot></a>
</template>

<script lang="ts">
import axios from "axios";
import { Component, Vue } from "vue-property-decorator";

const logoutUrl = "/accounts/logout/";

@Component
export default class LogOut extends Vue {
  async postLogOut() {
    try {
      const resp = await axios.post(logoutUrl);
    } catch {
      window.location.assign(logoutUrl);
      return;
    }
    window.location.assign("/");
  }
}
</script>

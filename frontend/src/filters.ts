import Vue from "vue";

import { Moment } from "moment";

export function formatDate(
  datetime: Moment | null,
  formatString?: string
): string | null {
  if (!datetime) {
    return null;
  }
  return datetime.format(formatString || "MMM D, YYYY");
}

Vue.filter("formatDate", formatDate);

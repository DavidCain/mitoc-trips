import moment from "moment";
import { Moment } from "moment";

// TODO: Import this from mitoc const
const RENEWAL_ALLOWED_WITH_DAYS_LEFT = 40;

// We should never prompt earlier than 2 days into the renewal period
// (2 days is a cautious guard against potential timezone problems w.r.t. dates)
const PADDED_RENEWAL_ALLOWED_WITH_DAYS_LEFT = Math.max(
  0,
  RENEWAL_ALLOWED_WITH_DAYS_LEFT - 2
);

// When a membership is nearing the end of its time, prompt users to renew!
const PROMPT_RENEWAL_WITH_DAYS_REMAINING = Math.min(
  30,
  PADDED_RENEWAL_ALLOWED_WITH_DAYS_LEFT
);

// The server should _always_ report one of these human-readable statuses
export type MembershipStatus =
  | "Active"
  | "Waiver Expired"
  | "Missing Waiver"
  | "Missing Membership"
  | "Expiring Soon"
  | "Expired"
  | "Missing";

/*
 * Returns true if:
 * 1. The date is some time in the future
 * 2. No more than `cutoff` days remain until that dote.
 */
function upToDaysRemaining(future: Moment | null, cutoff: number): boolean {
  if (!future) {
    return false;
  }
  const daysLeft = future.diff(moment(), "days");
  if (daysLeft === 0) {
    return future.diff(moment()) > 0;
  }
  return daysLeft > 0 && daysLeft <= cutoff;
}

/*
 * Returns true if:
 * 1. Renewing now would extend membership by a year, rather than resetting the year counter.
 * 2. It's close enough to the membership expiration date that we might prompt users to renew.
 */
export function expiringSoon(expiresOn: Moment | null): boolean {
  return upToDaysRemaining(expiresOn, PROMPT_RENEWAL_WITH_DAYS_REMAINING);
}

/*
 * Return if we're positive that renewing membership today would extend membership by one year.
 *
 * Towards the end of a one-year membership, we allow early renewal. This lets members ensure
 * that they have uninterrupted membership, while also not double-paying for the overlap period
 * if they pay for their next membership early (MITOC does not support automatic annual payments,
 * so this is a helpful mechanism).
 *
 * We add a couple days' cushion to be extremely sure that timezone differences do not affect the cutoff.
 */
export function earlyRenewalAllowed(expiresOn: Moment | null): boolean {
  return upToDaysRemaining(expiresOn, PADDED_RENEWAL_ALLOWED_WITH_DAYS_LEFT);
}

/**
 * Return the date that membership would be valid until if paying for a membership today.
 *
 * In normal circumstances (first membership or renewal), that's just one full year from today.
 * If early renewal is permitted, we add remaining valid membership onto the next one.
 */
export function expirationIfRenewingToday(expiresOn: Moment | null): Moment {
  if (expiresOn && earlyRenewalAllowed(expiresOn)) {
    // Copy, even if it's already a moment (add() modifies in place)
    return moment(expiresOn).add(1, "year");
  }
  // Default: One year from today
  return moment().add(1, "year");
}

export function statusIsActive(membershipStatus: MembershipStatus) {
  const activeStatuses = ["Active", "Expiring Soon"];
  return activeStatuses.includes(membershipStatus);
}

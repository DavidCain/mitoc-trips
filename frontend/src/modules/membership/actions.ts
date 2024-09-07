import axios from "axios";
import moment, { Moment } from "moment";

import { MembershipStatus } from "./status";
import { localize } from "@/modules/dateutil";

// Raw Membership & waiver representations, before being localized
interface RawMembership {
  email: string | null;
  expires: string | null; // An ISO-8601 date string, with implied EST/EDT
  active: boolean;
}
interface RawWaiver {
  expires: string | null; // An ISO-8601 date string, with implied EST/EDT
  active: boolean;
}

interface Membership {
  // Email address associated with the membership (null if not found)
  email: string | null;
  // Date on which the membership (paid dues) expires
  expires: Moment | null;
  // True if expires is some date in the future
  active: boolean;
}
interface Waiver {
  // Date on which the waiver expires
  expires: Moment | null; // An ISO-8601 date string, with implied EST/EDT
  // True if expires is some date in the future
  active: boolean;
}

// Example response, in raw JSON:
// {
//   membership: {
//     expires: "2019-03-08",
//     active: false,
//     email: "davidjosephcain@gmail.com"
//   },
//   waiver: { expires: "2020-02-02", active: true },
//   status: "Missing Dues"
// };
export interface MembershipResponse {
  membership: RawMembership;
  waiver: RawWaiver;
  status: MembershipStatus;
}

export interface MembershipData {
  membership: Membership;
  waiver: Waiver;
  membershipStatus: MembershipStatus;
}

function localizeExpiration(input: RawMembership | RawWaiver): Moment | null {
  return input.expires ? localize(moment(input.expires), true) : null;
}

export async function getMemberStatus(userId: number): Promise<MembershipData> {
  // TODO: We should probably handle cases like 404 (from a bad user ID), or other 500's
  const resp = await axios.get(`/users/${userId}/membership.json`);
  const data: MembershipResponse = resp.data;

  return {
    membership: {
      ...data.membership,
      expires: localizeExpiration(data.membership),
    },
    waiver: {
      ...data.waiver,
      expires: localizeExpiration(data.waiver),
    },
    membershipStatus: data["status"],
  };
}

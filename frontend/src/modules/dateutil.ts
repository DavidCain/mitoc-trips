/**
 * Some basic datetime utilities for working with times in Boston.
 *
 * It's generally really bad practice to write a datetime library yourself, and I'm not trying to do that here.
 * Rather, I'm trying to avoid injecting heavyweight dependencies for lightweight purposes.
 */
import moment, { Moment } from "moment";

/**
 * Return the start of DST, as observed on the East Coast in the United States.
 */
function startOfDst(datetime: Moment) {
  const marchFirst = datetime
    .clone()
    .utcOffset(-5, true) // Don't change wall time - it could alter date!
    .month("March")
    .startOf("month");
  const dow = marchFirst.day();
  const secondSundayMarch = marchFirst.add(7 + (dow ? 7 - dow : 0), "days");
  return secondSundayMarch.startOf("day").hour(2);
}

/**
 * Return the end of DST, as observed on the East Coast in the United States.
 */
function endOfDst(datetime: Moment) {
  const novemberFirst = datetime
    .clone()
    .utcOffset(-4, true) // Don't change wall time - it could alter date!
    .month("November")
    .startOf("month");
  const dow = novemberFirst.day();
  const firstSundayNovember = novemberFirst.add(dow ? 7 - dow : 0, "days");
  return firstSundayNovember.startOf("day").hour(2);
}

/**
 * Return the UTC offset observed by Boston, assuming DST observation.
/*
/* This is a hackish approximation of the current timezone observed in Boston.
 * It assumes that the given datetime will _always_ be a period of history in which
 * Boston observed DST according to the following rules:
 * * -4 UTC: Between the second Sunday of March (at 2 am) and the first Sunday of November (at 2 am),
 * * -5 UTC: All other times of year
 *
 * We use this homegrown method, rather than a proper timezone library since:
 * - This project aims to minimize dependencies & build size & the full momentjs tz lib is 40kb
 * - We only ever deal in one timezone (America/New_York)
 * - We _always_ assume dates & times are in America/New_York if not explicitly stated
 * - We do not have a lot of historical data to consider (all dates are early 21st century)
 *
 * @param datetime {Moment}: A datetime, with an accurate UTC offset
 */
export function bostonUtcOffset(datetime: Moment): number {
  const isDst =
    startOfDst(datetime) <= datetime && datetime < endOfDst(datetime);
  return isDst ? -4 : -5;
}

/**
 * Take a naive date (or datetime) and assign the proper UTC offset for Boston.
 *
 * Does _not_ change the wall time, only the offset attached to the time.
 *
 * Modifies datetime in-place!
 *
 * @param datetime {Moment}: A moment, which could have the user's local timezone applied, not necessarily Boston's!
 * @param keepTimezone {Boolean}: Unless true, replace the timezone with Boston's standard UTC offset
 *                                This handles the case of a local client parsing a simple date,
 *                                and (wrongly) assuming local timezone, which can differ from Boston's.
 */
export function localize(datetime: Moment, keepTimezone?: boolean): Moment {
  const correctedMoment = keepTimezone
    ? datetime
    : datetime.clone().utcOffset(-5, true);
  const offset = bostonUtcOffset(correctedMoment);

  // True indicates "preserve existing time of day" (do not translate)
  return datetime.utcOffset(offset, true);
}

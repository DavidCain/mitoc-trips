import moment, { Moment } from "moment";

export function setTimeTo(datestring: string | Moment): jest.SpyInstance {
  const mockedMoment = moment(datestring);
  return jest
    .spyOn(Date, "now")
    .mockImplementation(() => mockedMoment.valueOf());
}

import moment, { Moment } from "moment";

export function flushPromises() {
  /**
   * Flush all existing promises before proceeding with a test.
   *
   * Useful for ensuring that all HTTP promises resolve.
   * NOTE: This will cause problems if combined with Jest's timer mocks][timer-mocks]
   * https://github.com/facebook/jest/issues/7151
   *
   * We *could* use `setImmediate` to avoid `setTimeout` being mocked.
   * Indeed, that's what is done in the npm module `flush-promises`.
   * However, the method is not expected to become part of the standard.
   *
   * [timer-mocks]: https://jestjs.io/docs/en/timer-mocks
   */
  return new Promise(resolve => setTimeout(resolve));
}

export function setTimeTo(datestring: string | Moment): jest.SpyInstance {
  const mockedMoment = moment(datestring);
  return jest
    .spyOn(Date, "now")
    .mockImplementation(() => mockedMoment.valueOf());
}

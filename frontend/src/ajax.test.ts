import axios from "axios";
import MockAdapter from "axios-mock-adapter";
import { flushPromises } from "@/tests/util";
import configureAxios from "./ajax";

describe("configureAxios", () => {
  let mockAxios: MockAdapter;

  beforeEach(() => {
    mockAxios = new MockAdapter(axios);
  });

  it("uses different header names by default", async () => {
    mockAxios.onPost("/some-route").replyOnce(200);
    await axios.post("/some-route");
    flushPromises();
    const apiCall = mockAxios.history.post[0];
    // Note that these do NOT match what Django uses
    expect(apiCall.xsrfCookieName).toEqual("XSRF-TOKEN");
    expect(apiCall.xsrfHeaderName).toEqual("X-XSRF-TOKEN");
  });

  it("includes Django CSRF information in all requests", async () => {
    mockAxios.onPost("/some-route").replyOnce(200);
    configureAxios();
    await axios.post("/some-route");
    flushPromises();
    const apiCall = mockAxios.history.post[0];
    expect(apiCall.xsrfCookieName).toEqual("csrftoken");
    expect(apiCall.xsrfHeaderName).toEqual("X-CSRFTOKEN");
  });
});

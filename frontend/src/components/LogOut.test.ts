import axios from "axios";
import MockAdapter from "axios-mock-adapter";
import { shallowMount } from "@vue/test-utils";
import { flushPromises } from "@/tests/util";
import LogOut from "./LogOut.vue";

/* Source:  https://github.com/facebook/jest/issues/890#issuecomment-461935861 */
interface MockedLocation extends Location {
  assign: jest.Mock<void, [string]>;
}

interface MockedWindow extends Window {
  location: MockedLocation;
}

const baseUrl = "https://mitoc-trips.mit.edu";
export function mockWindow(win: Window = window, href = win.location.href) {
  const locationMocks: Partial<MockedLocation> = {
    assign: jest.fn().mockImplementation(replaceLocation)
  };

  return replaceLocation(href);

  function replaceLocation(url: string) {
    // @ts-ignore
    delete win.location;
    win.location = Object.assign(new URL(url, baseUrl), locationMocks) as any;
    return win as MockedWindow;
  }
}

describe("LogOut", () => {
  let mockAxios: MockAdapter;

  const saveLocation = window.location;

  beforeEach(() => {
    mockAxios = new MockAdapter(axios);
    mockWindow(window, "https://mitoc-trips.mit.edu/contact");
  });

  afterAll(() => {
    // @ts-ignore
    delete window.location;
    window.location = saveLocation;
  });

  it("posts to the logout route on click", async () => {
    const wrapper = shallowMount(LogOut, {
      slots: {
        default: "End session"
      }
    });
    expect(wrapper.text()).toEqual("End session");

    mockAxios.onPost("/accounts/logout/").replyOnce(200);
    wrapper.trigger("click");
    await flushPromises();

    const logOutCall = mockAxios.history.post[0];

    await flushPromises();
    // We successfully logged out, so redirect to the home page
    expect(window.location.href).toBe("https://mitoc-trips.mit.edu/");
  });

  it("redirects to the logout page on any API failure", async () => {
    const wrapper = shallowMount(LogOut, {
      slots: {
        default: "Log out"
      }
    });
    expect(wrapper.text()).toEqual("Log out");

    mockAxios.onPost("/accounts/logout/").replyOnce(403);
    wrapper.trigger("click");
    await flushPromises();

    const logOutCall = mockAxios.history.post[0];

    await flushPromises();
    // We failed to log out, so we redirect straight to the page
    expect(window.location.href).toBe(
      "https://mitoc-trips.mit.edu/accounts/logout/"
    );
  });
});

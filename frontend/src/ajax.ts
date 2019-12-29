import axios from "axios";

/**
 * Configure axios to always include Django's CSRF tokens on requests.
 *
 * Django will reject any POST that does not include a CSRF token.
 * It supplies these tokens via the cookie, but we need to configure
 * the correct header name & cookie name for axios to extract the token.
 */
export default function configureAxios(): void {
  axios.defaults.xsrfCookieName = "csrftoken";
  axios.defaults.xsrfHeaderName = "X-CSRFTOKEN";
}

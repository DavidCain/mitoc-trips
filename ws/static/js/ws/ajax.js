angular.module('ws.ajax', [])
.config(function($httpProvider) {
  // XHRs need to adhere to Django's expectations
  $httpProvider.defaults.xsrfCookieName = 'csrftoken';
  $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
});

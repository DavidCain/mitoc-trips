(function () {
  var dependencies = ['ui.bootstrap', 'ui.bootstrap.tpls',
                      'bcPhoneNumber',
                      'ws.ajax', 'ws.profile', 'ws.forms', 'ws.lottery', 'ws.trips', 'ws.widgets'];
  // Only inject Raven if it's available
  if (typeof Raven !== 'undefined') {
    dependencies.unshift('ngRaven');
  }

  angular.module('ws', dependencies);
})();

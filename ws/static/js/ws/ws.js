// Only inject Raven if it's available
(function () {
  // TODO: Make a custom AngularUI build with just the templates I need
  var dependencies = ['ui.gravatar',
                      'ui.bootstrap', 'ui.bootstrap.tpls', 'djng.forms',
                      'ws.ajax', 'ws.auth', 'ws.profile', 'ws.forms', 'ws.lottery', 'ws.stats', 'ws.widgets'];
  if (typeof Raven !== 'undefined') {
    dependencies.unshift('ngRaven');
  }

  angular.module('ws', dependencies);
})();

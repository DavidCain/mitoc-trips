// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ngRaven',
                      'ui.gravatar',
                      'ui.bootstrap', 'ui.bootstrap.tpls', 'djng.forms',
                      'ws.ajax', 'ws.auth', 'ws.profile', 'ws.forms', 'ws.lottery', 'ws.stats', 'ws.widgets']);

// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ui.bootstrap', 'ui.bootstrap.tpls', 'ng.django.forms',
                      'ws.ajax', 'ws.auth', 'ws.forms'])


angular.module('ws.ajax', [])
.config(function($httpProvider) {
  // XHRs need to adhere to Django's expectations
  $httpProvider.defaults.xsrfCookieName = 'csrftoken';
  $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
})


angular.module('ws.auth', ['ng.django.urls'])
.controller('authController', function($scope, $http, $window, djangoUrl) {
  $scope.logout = function(){
    var logoutUrl = djangoUrl.reverse('account_logout');
    $http.post(logoutUrl).then(function(){
      $window.location.href = '/'
    },
    function(){
      // Something probably went wrong with CSRF. Redirect to "you sure?" page
      $window.location.href = logoutUrl;
    });
  }
})


angular.module('ws.forms', ['ui.select', 'ngSanitize', 'ng.django.urls'])
// Taken from the AngularUI Select docs - filter by searched property
.filter('propsFilter', function() {
  return function(items, props) {
    var out = [];

    if (angular.isArray(items)) {
      items.forEach(function(item) {
        var itemMatches = false;

        var keys = Object.keys(props);
        for (var i = 0; i < keys.length; i++) {
          var prop = keys[i];
          var text = props[prop].toLowerCase();
          if (item[prop].toString().toLowerCase().indexOf(text) !== -1) {
            itemMatches = true;
            break;
          }
        }

        if (itemMatches) {
          out.push(item);
        }
      });
    } else {
      // Let the output be the input untouched
      out = items;
    }

    return out;
  };
})

.directive('leaderSelect', function($http, djangoUrl) {
  return {
    restrict: 'E',
    scope: {
      activity: '=?',
      selectedLeaders: '=ngModel',
    },
    templateUrl: '/static/template/leader-select.html',
    link: function (scope, element, attrs) {
      if (scope.selectedLeaders == null) { scope.selectedLeaders = []; }

      function fetchLeaderList(){
        var url = djangoUrl.reverse("json-leaders", [scope.activity]);
        $http.get(url).then(function (response){
          scope.leaders = response.data.leaders;
        });
      }
      fetchLeaderList();
      scope.$watch('activity', fetchLeaderList);
    }
  };
});

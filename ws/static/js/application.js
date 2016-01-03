// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ui.bootstrap', 'ui.bootstrap.tpls', 'ng.django.forms',
                      'ws.ajax', 'ws.auth', 'ws.forms', 'ws.lottery'])


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
      leaders: '=ngModel',
    },
    templateUrl: '/static/template/leader-select.html',
    link: function (scope, element, attrs) {
      //scope.name = attrs.name;
      if (scope.leaders == null) {
        // Annoying workaround since Djangular doesn't adhere to "dots in ng-models"
        // This relies upon the fact that the ng-model in the parent is also leaders
        // (Alternatively, we could override ng-models for good practice)
        scope.$parent.leaders = [];
      }
      scope.selected = {leaders: scope.$parent.leaders};

      function fetchLeaderList(){
        var url = djangoUrl.reverse("json-leaders", [scope.activity]);
        $http.get(url).then(function (response){
          scope.allLeaders = response.data.leaders;
        });
      }
      fetchLeaderList();
      scope.$watch('activity', fetchLeaderList);
      scope.$watch('selected.leaders', function(){
        scope.$parent.leaders = scope.selected.leaders
      });
    }
  };
});


angular.module('ws.lottery', ['ui.select', 'ui.sortable'])
.controller('lotteryController', function($scope, $http, $window) {
  $scope.ranked = $window.ranked; // Set in global via Django;
  $scope.submit = function(){
    var payload = {signups: $scope.ranked.signups,
                   car_status: $scope.car_status,
                   number_of_passengers: $scope.number_of_passengers};
    angular.extend(payload, $scope.car);
    $http.post('/preferences/lottery/', payload);
  }
})
.directive('tripRank', function(djangoUrl) {
  return {
    restrict: 'E',
    scope: {
      signups: '=',
    },
    templateUrl: '/static/template/trip-rank.html',
    link: function (scope, element, attrs) {
      scope.signups.forEach(function(signup){
        signup.deleted = false
      });

      // Assign trip signups the ranking given by the server
      scope.activeSignups = scope.signups.slice();  // We need object references
      var setOrder = function() {
        scope.activeSignups.forEach(function(signup, index){
          signup.order = index + 1;
        });
      }
      setOrder();

      // Whenever the ordering is changed, update the 'order' attributes
      scope.sortableOptions = {stop: setOrder};

      scope.deleteSignup = function (signup, index){
        signup.deleted = true;
        scope.activeSignups.splice(index, 1);
      }
    }
  }
});

angular.module('ws.lottery', ['ui.select', 'ui.sortable'])
.controller('lotteryController', function($scope, $http, $window) {
  $scope.ranked = {
    signups: JSON.parse(document.getElementById('jsonified-ranked-signups').textContent)
  };

  $scope.submit = function() {
    const payload = {
      signups: $scope.ranked.signups,  // Array of objects with `id`, `deleted`, and `order`
      car_status: $scope.car_status,
      number_of_passengers: $scope.number_of_passengers || null,
    };

    $http.post('/preferences/lottery/', payload).then(function() {
        $window.location.href = '/';
      },
      function() {
        $scope.submitError = true;
      }
    );
  };
})
.directive('tripRank', function() {
  return {
    restrict: 'E',
    scope: {
      signups: '=',
    },
    templateUrl: '/static/template/trip-rank.html',
    link: function (scope, element, attrs) {
      scope.signups.forEach(function(signup) {
        signup.deleted = false;
      });

      // Assign trip signups the ranking given by the server
      scope.activeSignups = scope.signups.slice();  // We need object references
      var setOrder = function() {
        scope.activeSignups.forEach(function(signup, index) {
          if (signup.order && signup.order !== index + 1) {
            scope.changesMade = true;
          }
          signup.order = index + 1;
        });
      };
      setOrder();

      // Whenever the ordering is changed, update the 'order' attributes
      scope.sortableOptions = {stop: setOrder};

      scope.deleteSignup = function (signup, index) {
        signup.deleted = true;
        scope.activeSignups.splice(index, 1);
        scope.changesMade = true;
      };
    }
  };
})
;

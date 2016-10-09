angular.module('ws.lottery', ['ui.select', 'ui.sortable'])
.controller('lotteryController', function($scope, $http, $window) {
  $scope.ranked = $window.ranked; // Set in global via Django;
  $scope.submit = function(){
    var payload = {signups: $scope.ranked.signups,
                   car_status: $scope.car_status,
                   number_of_passengers: $scope.number_of_passengers};
    angular.extend(payload, $scope.car);
    $http.post('/preferences/lottery/', payload).then(function() {
        $window.location.href = '/';
      },
      function(){
        $scope.submitError = true;
      }
    );
  };
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
        signup.deleted = false;
      });

      // Assign trip signups the ranking given by the server
      scope.activeSignups = scope.signups.slice();  // We need object references
      var setOrder = function() {
        scope.activeSignups.forEach(function(signup, index){
          signup.order = index + 1;
        });
      };
      setOrder();

      // Whenever the ordering is changed, update the 'order' attributes
      scope.sortableOptions = {stop: setOrder};

      scope.deleteSignup = function (signup, index){
        signup.deleted = true;
        scope.activeSignups.splice(index, 1);
      };
    }
  };
})
;

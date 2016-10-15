angular.module('ws.widgets', [])
.directive('carBadge', function() {
  return {
    restrict: 'E',
    scope: {
      numberOfPassengers: '=?',
      carStatus: '=',
    },
    templateUrl: '/static/template/car-badge.html',
    link: function (scope, element, attrs) {
      if (scope.carStatus === 'own') {
        scope.msg = 'Owns a car';
      } else if (scope.carStatus === 'rent') {
        scope.msg = 'Willing to rent';
      }

      if (scope.msg && scope.numberOfPassengers) {
        scope.msg += (', able to drive ' + scope.numberOfPassengers + ' passengers');
      }
    },
  };
});

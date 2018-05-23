angular.module('ws.trips', [])
.controller('tripTabManager', function($scope) {
  $scope.$on('tripModified', function() {
    $scope.stale = true;
  });
});

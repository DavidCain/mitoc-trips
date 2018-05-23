angular.module('ws.trips', [])
.controller('tripTabManager', function($scope, $window) {
  $scope.refreshIfStale = function() {
    if ($scope.stale) {
      $window.location.reload();
    }
  };

  $scope.$on('tripModified', function() {
    $scope.stale = true;
  });
});

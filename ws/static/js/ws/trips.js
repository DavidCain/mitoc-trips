angular.module('ws.trips', [])
.controller('tripTabManager', function($scope, $window) {
  $scope.$on('tripModified', function() {
    $scope.stale = true;
  });

  /**
   * Hack: just reload the page, this time telling Django we want a rental table.
   *
   * The reason that we control this via a GET argument is so that:
   *
   * 1. Leaders can quickly view trips without waiting for the rentals API call.
   * 2. If the API call fails for any reason, the page won't crash.
   * 3. We can render a full table
   *
   * The proper fix is to build a FE component which does
   */
  $scope.inlineRentals = function(tripId) {
    $scope.reloading = true;
    $window.location.assign('/trips/' + tripId + '?show_rentals_inline=1');
  }
});

angular.module('ws.auth', ['djng.urls'])
.controller('authController', function($scope, $http, $window, djangoUrl) {
  $scope.logout = function(){
    var logoutUrl = djangoUrl.reverse('account_logout');
    $http.post(logoutUrl).then(function(){
      $window.location.href = '/';
    },
    function(){
      // Something probably went wrong with CSRF. Redirect to "you sure?" page
      $window.location.href = logoutUrl;
    });
  };
});

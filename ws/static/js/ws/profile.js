angular.module('ws.profile', [])
.directive('editProfilePhoto', function($uibModal) {
  return {
    restrict: 'E',
    scope: {
      participantEmail: '@?',
      gravatarOptedOut: '='
    },
    template: "<button data-ng-click='openModal()' class='btn btn-default btn-xs'><i class='fas fa-lg fa-pencil-alt'></i></button>",
    link: function (scope, element, attrs) {
      scope.openModal = function() {
        $uibModal.open({
        templateUrl: '/static/template/edit-gravatar-modal.html',
        scope: scope
        });
      };
    }
  };
})
.directive('outstandingRentals', function($http, $filter) {
  return {
    restrict: 'E',
    scope: {
      userId: '=',
    },
    templateUrl: '/static/template/outstanding-rentals.html',
    link: function (scope, element, attrs) {
      scope.rentalMsg = '<p>All MITOC members are able to rent club gear at low prices.</p>' +
                        '<p>Want to learn more? Stop by during office hours or ' +
                        '<a href="https://mitoc.mit.edu/#rental">read about renting gear</a>.</p>';
      $http.get('/users/' + scope.userId + '/rentals.json')
        .then(function(resp) {
          scope.rentals = resp.data.rentals;
        });
    },
  };
})
;

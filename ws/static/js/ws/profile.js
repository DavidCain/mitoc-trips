angular.module('ws.profile', [])
.directive('editProfilePhoto', function($uibModal) {
  return {
    restrict: 'E',
    scope: {
      participantEmail: '@?'
    },
    template: "<button data-ng-click='openModal()' class='btn btn-default btn-xs'><i class='fa fa-lg fa-pencil'></i></button>",
    link: function (scope, element, attrs) {
      scope.openModal = function(){
        $uibModal.open({
        templateUrl: '/static/template/edit-gravatar-modal.html',
        scope: scope
        });
      };
    }
  };
})
.directive('membershipStatus', function($http, $filter){
  return {
    restrict: 'E',
    scope: {
      userId: '=',
      personal: '=?', // Give helpful messages, intended for when viewing own status
      showFullFaq: '=?',
    },
    templateUrl: '/static/template/membership-status.html',
    link: function (scope, element, attrs) {
      scope.labelClass = {
        'Active':         'label-success',
        'Waiver Expired': 'label-warning',
        'Missing Waiver': 'label-warning',
        'Expired':        'label-danger',
        'Missing':        'label-danger',
      };
      $http.get('/users/' + scope.userId + '/membership.json')
        .then(function(resp){
          scope.membership = resp.data.membership;
          scope.waiver = resp.data.waiver;
          scope.status = resp.data.status;
        });
    },
  };
})
.directive('outstandingRentals', function($http, $filter){
  return {
    restrict: 'E',
    scope: {
      userId: '=',
    },
    templateUrl: '/static/template/outstanding-rentals.html',
    link: function (scope, element, attrs) {
      scope.rentalMsg = '<p>All MITOC members are able to rent club gear at low prices.</p>' +
                        '<p>Want to learn more? Stop by during office hours or ' +
                        '<a href="http://mitoc.mit.edu/#rental">read about renting gear</a>.</p>';
      $http.get('/users/' + scope.userId + '/rentals.json')
        .then(function(resp){
          scope.rentals = resp.data.rentals;
        });
    },
  };
})
;

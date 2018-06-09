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
.value('membershipStatusLabels',
  {
    'Active':             'label-success',
    'Waiver Expired':     'label-warning',
    'Missing Waiver':     'label-warning',
    'Missing Membership': 'label-warning',
    'Expiring Soon':      'label-info',  // Special front-end only status
    'Expired':            'label-danger',
    'Missing':            'label-danger',
  }
)
.directive('membershipStatus', function($http, $filter, $timeout, membershipStatusLabels) {
  return {
    restrict: 'E',
    scope: {
      userId: '=',
      personal: '=?', // Give helpful messages, intended for when viewing own status
      showFullFaq: '=?',
      justSigned: '=?'  // Participant just finished signing a waiver
    },
    templateUrl: '/static/template/membership-status.html',
    link: function (scope, element, attrs) {
      scope.labelClass = membershipStatusLabels;

      // Return if the membership expires soon enough for renewal
      var expiringSoon = function(expiresOn) {
        var now = new Date();
        var msTilExpiry = expiresOn - now;
        return (msTilExpiry > 0) && (msTilExpiry < 2592000000);
      };

      var queriesPerformed = 0;  // Count queries made in attempt to get updated status

      // Spawns a membership check & returns true if participant just signed a waiver
      // (and the waiver status has not yet come in as active)
      var queryingAgain = function(waiverActive) {
        if (scope.justSigned && !waiverActive && queriesPerformed < 8) {
          queriesPerformed++;
          $timeout(queryStatus, 500 * queriesPerformed);
          return true;
        }
      };

      var queryStatus = function() {
        return $http.get('/users/' + scope.userId + '/membership.json')
          .then(function(resp) {
            if (queryingAgain(resp.data.waiver.active)) {
              return;  // Stop here - continuing would populate scope
            } else if (scope.justSigned) {
              scope.waiverUpdateSucceeded = resp.data.waiver.active;
            }

            scope.membership = resp.data.membership;
            scope.waiver = resp.data.waiver;
            scope.status = resp.data.status;

            // If personally viewing, allow a special status for "you should renew soon"
            var expiresOn = Date(scope.membership.expires);
            if (scope.personal && (scope.status === 'Active') && expiringSoon(expiresOn)) {
              scope.status = 'Expiring Soon';  // Some time in next 30 days

              // Add one year (setFullYear actually handles leap years!)
              scope.renewalValidUntil = new Date(expiresOn.valueOf());
              scope.renewalValidUntil.setFullYear(expiresOn.getFullYear() + 1);
            }
          });
      };
      queryStatus();
    },
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
                        '<a href="http://mitoc.mit.edu/#rental">read about renting gear</a>.</p>';
      $http.get('/users/' + scope.userId + '/rentals.json')
        .then(function(resp) {
          scope.rentals = resp.data.rentals;
        });
    },
  };
})
;

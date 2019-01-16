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

      var daysUntil = function(dateString) {
        var msDiff = (new Date(dateString)) - (new Date());
        return Math.floor(msDiff / 86400000);
      };

      // Return if the membership expires soon enough for renewal
      var expiringSoon = function(expiresOn) {
        var daysLeft = daysUntil(expiresOn);
        return (daysLeft > 0) && (daysLeft < 30);
      };

      var queriesPerformed = 0;  // Count queries made in attempt to get updated status
      var maxQueries = 8;

      // If the waiver is valid for a year, we know a recent one was received
      // (less than a year to be sure leap days and tz conversion are irrelevant)
      var waiverUpdateReceived = function(waiverExpires) {
        return waiverExpires && daysUntil(waiverExpires) >= 363;
      };

      // Spawns a membership check & returns true if still waiting on the update
      var queryingAgain = function(waiverExpires) {
        var updateReceived = waiverUpdateReceived(waiverExpires);
        if (scope.justSigned && !updateReceived && queriesPerformed < maxQueries) {
          queriesPerformed++;
          $timeout(queryStatus, 500 * queriesPerformed);
          return true;
        }
      };

      var queryStatus = function() {
        return $http.get('/users/' + scope.userId + '/membership.json')
          .then(function(resp) {
            var waiverExpires = resp.data.waiver.expires;
            if (queryingAgain(waiverExpires)) {
              return;  // Stop here - continuing would populate scope
            } else if (scope.justSigned) {
              scope.waiverUpdateSucceeded = waiverUpdateReceived(waiverExpires);
            }

            scope.membership = resp.data.membership;
            scope.waiver = resp.data.waiver;
            scope.status = resp.data.status;

            // If personally viewing, allow a special status for "you should renew soon"
            var expiresOn = new Date(scope.membership.expires);
            if (scope.personal && (scope.status === 'Active') && expiringSoon(expiresOn.valueOf())) {
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
                        '<a href="https://mitoc.mit.edu/#rental">read about renting gear</a>.</p>';
      $http.get('/users/' + scope.userId + '/rentals.json')
        .then(function(resp) {
          scope.rentals = resp.data.rentals;
        });
    },
  };
})
;

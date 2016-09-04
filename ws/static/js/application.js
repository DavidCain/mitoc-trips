// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ui.bootstrap', 'ui.bootstrap.tpls', 'djng.forms',
                      'ws.ajax', 'ws.auth', 'ws.profile', 'ws.forms', 'ws.lottery', 'ws.widgets']);


angular.module('ws.ajax', [])
.config(function($httpProvider) {
  // XHRs need to adhere to Django's expectations
  $httpProvider.defaults.xsrfCookieName = 'csrftoken';
  $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
});


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
      if (scope.carStatus === 'own'){
        scope.msg = 'Owns a car';
      } else if (scope.carStatus === 'rent'){
        scope.msg = 'Willing to rent';
      }

      if (scope.msg && scope.numberOfPassengers){
        scope.msg += (', able to drive ' + scope.numberOfPassengers + ' passengers');
      }
    },
  };
});

angular.module('ws.forms', ['ui.select', 'ngSanitize', 'djng.urls'])
// Taken from the AngularUI Select docs - filter by searched property
.filter('propsFilter', function() {
  return function(items, props) {
    var out = [];

    if (angular.isArray(items)) {
      items.forEach(function(item) {
        var itemMatches = false;

        var keys = Object.keys(props);
        for (var i = 0; i < keys.length; i++) {
          var prop = keys[i];
          var text = props[prop].toLowerCase();
          if (item[prop].toString().toLowerCase().indexOf(text) !== -1) {
            itemMatches = true;
            break;
          }
        }

        if (itemMatches) {
          out.push(item);
        }
      });
    } else {
      // Let the output be the input untouched
      out = items;
    }

    return out;
  };
})
.controller('leaderRating', function($scope, $http, djangoUrl) {
  $scope.$watchGroup(['participant', 'activity'], function(){
    if ($scope.participant && $scope.activity) {
      var getRatingUrl = '/leaders/' + $scope.participant +
                         '/ratings/' + $scope.activity + '.json';
      $http.get(getRatingUrl).then(function (response){
        $scope.rating = response.data.rating;
        $scope.notes = response.data.notes;
      });
    }
  });
})
.directive('editableSignupList', function() {
  return {
    restrict: 'E',
    scope: {
      signups: '=',
      hideFeedback: '=',
      sortableOptions: '=',
      deleteSignup: '='
    },
    templateUrl: '/static/template/editable-signup-list.html',
  };
})
.directive('emailTripMembers', function(){
  return {
    restrict: 'E',
    scope: {
      signups: '=',
    },
    templateUrl: '/static/template/email-trip-members.html',
    link: function (scope, element, attrs) {

      scope.showEmails = {
        onTrip: true,
        waitlist: false,
      };

      var updateEmailText = function(){
        /* Update participant emails according to the selected buttons. */
        var signups = [];
        if (scope.signups.waitlist && scope.signups.waitlist.length){
          for (var sublist in scope.showEmails) {
            if (scope.showEmails[sublist]) {
              if (scope.signups[sublist]){
                signups = signups.concat(scope.signups[sublist]);
              }
            }
          }
        } else {
          // If there's no waitlist, don't bother honoring the buttons
          // (we'll be hiding the controls anyway)
          signups = scope.signups.onTrip || [];
        }

        var emails = signups.map(function(signup){
          return signup.participant.name + ' <' + signup.participant.email + '>';
        });
        scope.emailText = emails.join(', ');
      };

      scope.$watch('signups', updateEmailText, true);
      scope.$watch('showEmails',  updateEmailText, true);
    }
  };
})
.directive('adminTripSignups', function($http, filterFilter, $window, $uibModal) {
  return {
    restrict: 'E',
    scope: {
      tripId: '=',
      maximumParticipants: '=',
    },
    templateUrl: '/static/template/admin-trip-signups.html',
    link: function (scope, element, attrs) {
      scope.signups = {};  // Signups, broken into normal + waiting list

      var url = '/trips/' + scope.tripId + '/admin/signups/';
      $http.get(url).then(function(response){
        scope.allSignups = response.data.signups;
        updateSignups();
      });

      scope.deleteSignup = function(signup){
        signup.deleted = !signup.deleted;
        updateSignups();
      };

      var updateSignups = function(removeDeleted){
        /* Break all signups into "on trip" and waitlisted signups */
        if (!scope.allSignups){  // Happens when maximum participants changes
          return;
        } else if (scope.signups.waitlist){
          scope.allSignups = scope.signups.onTrip.concat(scope.signups.waitlist);
        }

        scope.onTripCount = 0;
        scope.signups.onTrip = [];
        scope.signups.waitlist = [];
        scope.allSignups.forEach(function(signup, index){
          if (removeDeleted && signup.deleted){ return; }

          if (scope.onTripCount < scope.maximumParticipants){
            scope.signups.onTrip.push(signup);
            if (!signup.deleted){
              scope.onTripCount++;
            }
          } else {
            scope.signups.waitlist.push(signup);
          }
        });
      };

      // So we can use 'updateSignups' as a callback even with truthy first arg
      var updateKeepDeleted = function(){
        updateSignups(false);
      };
      scope.sortableOptions = {stop: updateKeepDeleted,
                               connectWith: '.signup-list'};
      scope.$watch('maximumParticipants', updateKeepDeleted);

      scope.verifyChanges = function(){
        scope.modal = $uibModal.open({
          templateUrl: '/static/template/admin-trip-signups-modal.html',
          scope: scope
        });
      };

      scope.submit = function(){
        var signups = scope.allSignups.map(function(signup){
          return {id: signup.id,
                  deleted: signup.deleted,
                  participant: signup.participant};
        });
        var payload = {signups: signups,
                       maximum_participants: scope.maximumParticipants};
        $http.post(url, payload).then(function(){
          scope.modal.dismiss('success');
          updateSignups(true);  // Remove the deleted signups
        }, function(response){
          scope.error = "A server error occurred. Please contact the administrator";
        });
      };
    }
  };
})
.directive('delete', function($http, $window, $uibModal) {
  return {
    restrict: 'E',
    scope: {
      objId: '=',
      apiSlug: '@'
    },
    templateUrl: '/static/template/delete.html',
    link: function (scope, element, attrs) {
      scope.deleteObject = function(){
        if (!scope.apiSlug || !scope.objId){
          scope.error = "Object unknown; unable to delete";
        }
        $http.post('/' + scope.apiSlug + '/' + scope.objId + '/delete/').then(function(){
          $window.location.href = '/';
        },
        function(){
          scope.error = "An error occurred deleting the object.";
        });
      };
      scope.confirmDelete = function(){
        $uibModal.open({
          templateUrl: '/static/template/delete-modal.html',
          scope: scope
        });
      };
    }
  };
})
/* Expects leaders represented as in json-leaders. */
.service('activityService', function(){
  var open_activities = ['circus', 'official_event', 'course'];

  var activityService = this;

  /* Return if the activity is open to all leaders */
  activityService.isOpen = function(activity){
    return _.includes(open_activities, activity);
  };

  /* Give a string representation of the leader's applicable rating.
   *
   * When the activity is Winter School, this might return 'B coC'
   * When it's an open activity, an empty string will be returned
   */
  activityService.formatRating = function(activity, leader){
    if (!activity || activityService.isOpen(activity)){
      return "";
    }
    var leader_rating = _.find(leader.ratings, {activity: activity});
    return leader_rating && leader_rating.rating;
  };

  /* Return if the person is rated to lead the activity. */
  activityService.leaderRated = function(activity, leader){
    if (activityService.isOpen(activity)){
      return !!leader.ratings.length;
    }

    var rating = _.find(leader.ratings, {activity: activity});
    return !!rating;
  };
})
.directive('leaderSelect', function($http, djangoUrl, filterFilter, activityService) {
  return {
    restrict: 'E',
    require: 'ngModel',
    scope: {
      activity: '=?',
      leaders: '=ngModel',
      leaderIds: '=?',  // Existing IDs, supplied through widget
      name: '@'
    },
    templateUrl: '/static/template/leader-select.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.selected = {};

      /* Fetch all leaders and their ratings */
      function fetchLeaderList(){
        $http.get(djangoUrl.reverse("json-leaders")).then(function (response){
          scope.allLeaders = response.data.leaders;

          // Match IDs of leaders (supplied in directive attr) to leaders
          if (scope.leaderIds && scope.leaderIds.length){
            scope.selected.leaders = _.filter(scope.allLeaders, function(leader){
              return _.includes(scope.leaderIds, leader.id);
            });
            delete scope.leaderIds;  // Not used elsewhere, prevent doing this again
          }
          filterForActivity();
        });
      }
      fetchLeaderList();  // Only called here, but could feasibly want to refresh

      /* Filter the select options to only include leaders for the current activity
       *
       * Additionally, the `ratings` field present on all leaders will be replaced
       * with their activity-appropriate rating.
       */
      function filterForActivity(){
        if (!scope.allLeaders){
          return;
        }

        var filteredLeaders;
        if (!scope.activity || activityService.isOpen(scope.activity)){
          scope.filteredLeaders = scope.allLeaders;
        } else {
          var hasRating = {ratings: {activity: scope.activity}};
          scope.filteredLeaders = filterFilter(scope.allLeaders, hasRating);
        }

        // Add a single 'rating' attribute that corresponds to the activity
        // (for easy searching of leaders by rating)
        _.each(scope.filteredLeaders, function(leader){
          leader.rating = activityService.formatRating(scope.activity, leader);
        });
      }

      // (Enable Djangular to display errors on the required validator)
      ngModelCtrl.$isEmpty = function(leaders){
        return !(leaders && leaders.length);
      };

      ngModelCtrl.$validators.leadersOkay = function(modelValue, viewValue){
        return _.every(_.map(viewValue, 'canLead'));
      };

      ngModelCtrl.$formatters.push(function(modelValue) {
        return _.filter(scope.allLeaders, function(leader){
          return _.contains(modelValue, leader.id);
        });
      });

      ngModelCtrl.$render = function() {
        scope.selected.leaders = ngModelCtrl.$viewValue;
      };

      /* Annotate all selected leaders with an attribute indicating whether
       * or not they can lead the trip.
       */
      var checkSelectedLeaders = function(){
        var checkLeader = _.partial(activityService.leaderRated, scope.activity);
        _.each(scope.selected.leaders, function(leader){
          leader.canLead = checkLeader(leader);
        });
      };

      scope.$watch('activity', filterForActivity);
      scope.$watch('activity', checkSelectedLeaders);
      scope.$watch('activity', ngModelCtrl.$validate);

      scope.$watch('selected.leaders', function() {
        checkSelectedLeaders();
        ngModelCtrl.$setViewValue(scope.selected.leaders);
      });

      ngModelCtrl.$parsers.push(function(viewValue) {
        return _.map(viewValue, 'id');
      });
    }
  };
});


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
});

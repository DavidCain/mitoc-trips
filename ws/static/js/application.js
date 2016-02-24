// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ui.bootstrap', 'ui.bootstrap.tpls', 'ng.django.forms',
                      'ws.ajax', 'ws.auth', 'ws.forms', 'ws.lottery', 'ws.widgets'])


angular.module('ws.ajax', [])
.config(function($httpProvider) {
  // XHRs need to adhere to Django's expectations
  $httpProvider.defaults.xsrfCookieName = 'csrftoken';
  $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
})


angular.module('ws.auth', ['ng.django.urls'])
.controller('authController', function($scope, $http, $window, djangoUrl) {
  $scope.logout = function(){
    var logoutUrl = djangoUrl.reverse('account_logout');
    $http.post(logoutUrl).then(function(){
      $window.location.href = '/'
    },
    function(){
      // Something probably went wrong with CSRF. Redirect to "you sure?" page
      $window.location.href = logoutUrl;
    });
  }
})


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
    }
  }
})

angular.module('ws.forms', ['ui.select', 'ngSanitize', 'ng.django.urls'])
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
  })
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
  }
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
  }
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
      }

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
      }
      scope.sortableOptions = {stop: updateKeepDeleted,
                               connectWith: '.signup-list'};
      scope.$watch('maximumParticipants', updateKeepDeleted);

      scope.verifyChanges = function(){
        scope.modal = $uibModal.open({
          templateUrl: '/static/template/admin-trip-signups-modal.html',
          scope: scope
        })
      }

      scope.submit = function(){
        var signups = scope.allSignups.map(function(signup){
          return {id: signup.id,
                  deleted: signup.deleted,
                  participant: signup.participant};
        });
        var payload = {signups: signups,
                       maximum_participants: scope.maximumParticipants}
        $http.post(url, payload).then(function(){
          scope.modal.dismiss('success');
          updateSignups(true);  // Remove the deleted signups
        }, function(response){
          scope.error = "A server error occurred. Please contact the administrator";
        });
      }
    }
  }

})

.directive('deleteTrip', function($http, $window, $uibModal) {
  return {
    restrict: 'E',
    scope: {
      tripId: '=',
    },
    templateUrl: '/static/template/delete-trip.html',
    link: function (scope, element, attrs) {
      scope.deleteTrip = function(){
        $http.post('/trips/' + scope.tripId + '/delete/').then(function(){
          $window.location.href = '/';
        },
        function(){
          scope.error = "An error occurred deleting the trip.";
        });
      }
      scope.confirmDeleteTrip = function(){
        $uibModal.open({
          templateUrl: '/static/template/delete-trip-modal.html',
          scope: scope
        })
      }
    }
  }
})
.directive('leaderSelect', function($http, djangoUrl) {
  return {
    restrict: 'E',
    scope: {
      activity: '=?',
      leaders: '=ngModel',
    },
    templateUrl: '/static/template/leader-select.html',
    link: function (scope, element, attrs) {
      //scope.name = attrs.name;
      if (scope.leaders == null) {
        // Annoying workaround since Djangular doesn't adhere to "dots in ng-models"
        // This relies upon the fact that the ng-model in the parent is also leaders
        // (Alternatively, we could override ng-models for good practice)
        scope.$parent.leaders = [];
      }
      scope.selected = {leaders: scope.$parent.leaders};

      function fetchLeaderList(){
        var url = djangoUrl.reverse("json-leaders", [scope.activity]);
        $http.get(url).then(function (response){
          scope.allLeaders = response.data.leaders;
        });
      }
      fetchLeaderList();
      scope.$watch('activity', fetchLeaderList);
      scope.$watch('selected.leaders', function(){
        scope.$parent.leaders = scope.selected.leaders
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
  }
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
        signup.deleted = false
      });

      // Assign trip signups the ranking given by the server
      scope.activeSignups = scope.signups.slice();  // We need object references
      var setOrder = function() {
        scope.activeSignups.forEach(function(signup, index){
          signup.order = index + 1;
        });
      }
      setOrder();

      // Whenever the ordering is changed, update the 'order' attributes
      scope.sortableOptions = {stop: setOrder};

      scope.deleteSignup = function (signup, index){
        signup.deleted = true;
        scope.activeSignups.splice(index, 1);
      }
    }
  }
});

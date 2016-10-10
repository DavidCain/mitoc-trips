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
.directive('submitIfValid', function($compile) {
  return {
    restrict: 'A',
    require: 'form',
    link: function (scope, element, attrs, formCtrl) {
      if (!element.attr('data-ng-submit')){
        element.attr('data-ng-submit', 'submit($event)');
        return $compile(element)(scope);
      }

      scope.submit = function($event){
        formCtrl.$setSubmitted();
        if (formCtrl.$valid) {
          return;  // Form should have normal action, submits normally
        }

        // Manually mark fields as dirty to display Django-Angular errors
        angular.forEach(formCtrl.$error, function (field) {
          angular.forEach(field, function(errorField){
            errorField.$setDirty();
          })
        });

        // Stop form submission so client validation displays
        $event.preventDefault();
      };

    }
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
    link: function (scope, element, attrs) {
      // TODO: Copy-pasted. Make this common to two places it's used
      scope.labelClass = {
        'Active':         'label-success',
        'Waiver Expired': 'label-warning',
        'Missing Waiver': 'label-warning',
        'Expired':        'label-danger',
        'Missing':        'label-danger',
      };
    },
  };
})
.directive('emailTripMembers', function($http, djangoUrl){
  return {
    restrict: 'E',
    scope: {
      signups: '=?',
      leaders: '=?',
      creator: '=?',
      // If the above values are present, we'll use those. Otherwise, fetch from trip.
      tripId: '=?',
    },
    templateUrl: '/static/template/email-trip-members.html',
    link: function (scope, element, attrs) {
      if (scope.tripId && !_.every([scope.creator, scope.leaders, scope.signups])) {
        $http.get(djangoUrl.reverse('json-signups', [scope.tripId]))
          .success(function(data){
            scope.signups = data.signups;
            scope.leaders = data.leaders;
            scope.creator = data.creator;
            if (!scope.leaders.length) {
              scope.showEmails.creator = true;
            }
            if (scope.signups.onTrip.length) {
              scope.showEmails.onTrip = true;
            }
          });
      }

      scope.showEmails = {
        creator: false,
        onTrip: false,
        waitlist: false,
        leaders: false,
      };

      var updateEmailText = function(){
        if (_.isEmpty(scope.signups)) {
          return;
        }

        // Disallow an empty selection by defaulting to some reasonable default
        if (!_.some(_.values(scope.showEmails))) {
          if (scope.signups.onTrip.length) {
            scope.showEmails.onTrip = true;
          } else if (scope.leaders.length) {
            scope.showEmails.leaders = true;
          } else {
            scope.showEmails.creator = true;
          }
        }

        /* Update participant emails according to the selected buttons. */
        var signups = [];
        ['onTrip', 'waitlist'].forEach(function(subList) {
          if (scope.showEmails[subList] && scope.signups[subList]){
            signups = signups.concat(scope.signups[subList]);
          }
        });

        // TODO: Make a service out of this
        var formatEmail = function(participant){
          return participant.name + ' <' + participant.email + '>';
        };

        var emails = [];
        if (scope.showEmails.creator) {
          emails.push(formatEmail(scope.creator));
        }
        if (scope.showEmails.leaders) {
          // Avoid repeating the creator if they're also a leader
          // But if both options (Creator & Leader) are selected, order creator first
          var leaderEmails = scope.leaders.map(formatEmail);
          if (scope.showEmails.creator) {
            leaderEmails = _.difference(leaderEmails, emails);
          }
          emails = emails.concat(leaderEmails);
        }
        emails = emails.concat(signups.map(function(signup) {
          return formatEmail(signup.participant);
        }));

        scope.emailText = emails.join(', ');
      };

      scope.$watch('signups', updateEmailText, true);
      scope.$watch('showEmails', updateEmailText, true);
    }
  };
})
.directive('adminTripSignups', function($http, filterFilter, $window, $uibModal, djangoUrl) {
  return {
    restrict: 'E',
    scope: {
      tripId: '=',
      maximumParticipants: '=',
    },
    templateUrl: '/static/template/admin-trip-signups.html',
    link: function (scope, element, attrs) {
      scope.signups = {};  // Signups, broken into normal + waiting list
      scope.lapsedMembers = {};  // Also broken into normal + waiting list

      var url = '/trips/' + scope.tripId + '/admin/signups/';
      $http.get(url).then(function(response){
        scope.allSignups = response.data.signups;
        scope.leaders = response.data.leaders;
        scope.creator = response.data.creator;
        updateSignups();
        return _.map(scope.allSignups, 'participant.id');
      }).then(function(participant_ids) {
        var url = djangoUrl.reverse("membership_statuses");
        return $http.post(url, {participant_ids: participant_ids});
      }).then(function(response){
        /* Query the geardb server for membership status.
         *
         * It's possible this query will hang or otherwise not complete
         * (due to SIPB Scripts' lousy SQL uptime).
         */
        var memberships = response.data.memberships;
        scope.allSignups.forEach(function(signup){
          var participant = signup.participant;
          participant.membership = memberships[participant.id];
          var email = '<' + participant.name + '> ' + participant.email;
          participant.formattedEmail = email;
        });
        updateLapsedMembers();
      });

      scope.deleteSignup = function(signup){
        signup.deleted = !signup.deleted;
        updateSignups();
      };

      var membershipLapsed = {participant: {membership: {status: "!Active"}}};
      var updateLapsedMembers = function() {
        ['onTrip', 'waitlist'].forEach(function(subList) {
          var lapsedSignups = filterFilter(scope.signups[subList], membershipLapsed);
          scope.lapsedMembers[subList] = _.map(lapsedSignups, 'participant.formattedEmail');
        });
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

        // Will be a no-op if signups lack membership status
        updateLapsedMembers();
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
.directive('dangerHover', function($compile) {
  return {
    restrict: 'A',
    link: function (scope, element, attrs) {
      // Identify the base Bootstrap button class to display when not hovering
      var classes = attrs.class ? attrs.class.split(/\s+/) : [];
      var baseBtnClass = attrs.class && _.find(classes, function (cls) {
        return cls.lastIndexOf('btn-', 0) === 0;
      });
      if (!baseBtnClass) {
        baseBtnClass = 'btn-default';
        element.addClass('btn');
        element.addClass(baseBtnClass);
      }

      // Show red when hovering
      element.bind('mouseover', function(e) {
        element.removeClass(baseBtnClass);
        element.addClass('btn-danger');
      });
      element.bind('mouseleave', function(e) {
        element.removeClass('btn-danger');
        element.addClass(baseBtnClass);
      });
    },
  };
})
.directive('delete', function($http, $window, $uibModal) {
  return {
    restrict: 'E',
    scope: {
      objId: '=',
      apiSlug: '@',
      label: '@?',
    },
    replace: true,  // So that .btn will be styled appropriately in btn-group
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
.directive('participantSelect', function($http, djangoUrl) {
  return {
    restrict: 'E',
    require: '?ngModel',
    scope: {
      msg: '=?',
    },
    templateUrl: '/static/template/participant-select.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.msg = scope.msg || "Search participants...";
      scope.participants = {};

      if (ngModelCtrl) {
        ngModelCtrl.$render = function() {
          scope.participants.selected = ngModelCtrl.$viewValue;
        };
        scope.$watch('participants.selected', function(newval, oldval) {
          if( newval !== oldval ) {
            ngModelCtrl.$setViewValue(newval);
          }
        });
      }

      var url = djangoUrl.reverse("json-participants");
      scope.getMatchingParticipants = function(search) {
        $http.get(url, {params: {search: search}}).then(function (response) {
          scope.participants.all = response.data.participants;
        });
      };

      scope.getMatchingParticipants();
    },
  };
})
.directive('flakingParticipants', function($http){
  return {
    restrict: 'E',
    templateUrl: '/static/template/flaking-participants.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.participants = {flakes: []};

      scope.addFlake = function(participant) {
        if (!_.find(scope.participants.flakes, {id: participant.id})){
          scope.participants.flakes.push(participant);
        }
        scope.flake = null;
      };

      scope.removeFlake = function(participant) {
        parIndex = _.findIndex(scope.participants.flakes, {id: participant.id});
        if (parIndex !== -1){
          scope.participants.flakes.splice(parIndex, 1);
        }
      };
    },
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
      var fetchLeaderList = function() {
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
      var filterForActivity = function() {
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
          return _.includes(modelValue, leader.id);
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

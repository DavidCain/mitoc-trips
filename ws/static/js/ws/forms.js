angular.module('ws.forms', ['ui.select', 'ngSanitize', 'djng.urls'])
.factory('formatEmail', function () {
  return function (participant) {
    return participant.name + ' <' + participant.email + '>';
  };
})
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
      if (!element.attr('data-ng-submit')) {
        element.attr('data-ng-submit', 'submit($event)');
        return $compile(element)(scope);
      }

      scope.submit = function($event) {
        formCtrl.$setSubmitted();
        if (formCtrl.$valid) {
          return;  // Form should have normal action, submits normally
        }

        // Ugly hack to work around bug I can't identify.
        // When the participant is present & valid, form validation still marks it
        // as "required" with an undefined $modelValue
        if (_.isEqual(_.keys(formCtrl.$error), ["required"])) {
          var req = formCtrl.$error.required;
          var justParticipant = req.length === 1 && req[0].$name === 'participant';
          if (justParticipant && formCtrl.participant.$valid) {
            return;
          }
        }

        // Manually mark fields as dirty to display Django-Angular errors
        angular.forEach(formCtrl.$error, function (field) {
          angular.forEach(field, function(errorField) {
            errorField.$setDirty();
          });
        });

        // Stop form submission so client validation displays
        $event.preventDefault();
      };

    }
  };
})
.controller('leaderRating', function($scope, $http, djangoUrl) {
  $scope.$watchGroup(['participant', 'activity'], function() {
    if ($scope.participant && $scope.activity) {
      var args = [$scope.participant.id, $scope.activity];
      var getRatingUrl = djangoUrl.reverse('json-ratings', args);
      $http.get(getRatingUrl).then(function (response) {
        $scope.rating = response.data.rating;
        $scope.notes = response.data.notes;
      });
    }
  });
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
.directive('editableSignupList', function(membershipStatusLabels) {
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
      scope.labelClass = membershipStatusLabels;
    },
  };
})
.directive('emailTripMembers', function($http, djangoUrl, formatEmail) {
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
          .success(function(data) {
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

      // Start out with defaults (may be modified depending on what's feasible)
      scope.showEmails = {
        creator: true,
        onTrip: true,
        waitlist: false,
        leaders: false,
      };

      /* Disallow an empty list of emails
       * Set a default if signups change or the user tries to deselect all buttons
       */
      var ensureNonEmptySelection = function() {
        // Determine which buttons would display a valid list of emails
        var viability = {
          creator: scope.leaders.length !== 1,  // We'll only use "leaders" in this case
          onTrip: scope.signups.onTrip.length,
          waitlist: scope.signups.waitlist.length,
          leaders: scope.leaders.length,
        };

        // Determine which selectors are viable, disable any that are not
        var viableOptions = _.pickBy(scope.showEmails, function(value, key) {
          var isViable = viability[key];
          if (!isViable) { scope.showEmails[key] = false; }
          return isViable;
        });

        // If none of the selected options are viable, set the first one to true
        if (!_.some(_.values(viableOptions))) {
          scope.showEmails[_.keys(viableOptions)[0]] = true;
        }

        // Determine which selectors to display (invalid buttons should be hidden)
        scope.display = _.mapValues(scope.showEmails, function(value, key) {
          return _.has(viableOptions, key);
        });
      };

      var updateEmailText = function() {
        if (_.isEmpty(scope.signups)) {
          return;
        }

        ensureNonEmptySelection();

        /* Update trip member emails according to the selected buttons. */
        var emails = [];

        if (scope.showEmails.leaders) {
          emails = scope.leaders.map(formatEmail);
        }

        var signups = [];
        ['onTrip', 'waitlist'].forEach(function(subList) {
          if (scope.showEmails[subList] && scope.signups[subList]) {
            signups = signups.concat(scope.signups[subList]);
          }
        });
        emails = emails.concat(signups.map(function(signup) {
          return formatEmail(signup.participant);
        }));

        if (scope.showEmails.creator) {
          var creatorEmail = formatEmail(scope.creator);
          // Don't repeat creator if they're also a leader or participant
          _.pull(emails, creatorEmail);
          emails.unshift(creatorEmail);
        }

        scope.emailText = emails.join(', ');
      };

      scope.$watch('signups', updateEmailText, true);
      scope.$watch('showEmails', updateEmailText, true);
    }
  };
})
.directive('adminTripSignups', function($http, filterFilter, $window, $uibModal, djangoUrl, formatEmail) {
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

      var updateSignups = function(removeDeleted) {
        /* Break all signups into "on trip" and waitlisted signups */
        if (!scope.allSignups) {  // Happens when maximum participants changes
          return;
        } else if (scope.signups.waitlist) {
          scope.allSignups = scope.signups.onTrip.concat(scope.signups.waitlist);
        }
        if (removeDeleted) {
          _.remove(scope.allSignups, {deleted: true});
        }

        scope.onTripCount = 0;
        scope.signups.onTrip = [];
        scope.signups.waitlist = [];
        scope.allSignups.forEach(function(signup) {
          if (scope.onTripCount < scope.maximumParticipants) {
            scope.signups.onTrip.push(signup);
            if (!signup.deleted) {
              scope.onTripCount++;
            }
          } else {
            scope.signups.waitlist.push(signup);
          }
        });

        // Will be a no-op if signups lack membership status
        updateLapsedMembers();
      };

      /* Query the geardb server for membership status.
       *
       * It's possible this query will hang or otherwise not complete
       * (due to SIPB Scripts' lousy SQL uptime).
       */
      var updateSignupMemberships = function() {
        var participantIds = _.map(scope.allSignups, 'participant.id');
        if (participantIds.length === 0) {
          return;
        }
        var url = djangoUrl.reverse("json-membership_statuses");
        $http.post(url, {participant_ids: participantIds}).then(function(response) {
          var memberships = response.data.memberships;
          scope.allSignups.forEach(function(signup) {
            signup.participant.membership = memberships[signup.participant.id];
          });
          updateLapsedMembers();
        });
      };

      var formatSignupEmail = function (signup) {
        signup.participant.formattedEmail = formatEmail(signup.participant);
      };

      var url = djangoUrl.reverse('json-admin_trip_signups', [scope.tripId]);
      $http.get(url).then(function(response) {
        scope.allSignups = response.data.signups;
        scope.allSignups.forEach(formatSignupEmail);
        scope.leaders = response.data.leaders;
        scope.creator = response.data.creator;
        updateSignups();
      }).then(updateSignupMemberships);

      scope.deleteSignup = function(signup) {
        signup.deleted = !signup.deleted;
        updateSignups();
      };

      scope.addParticipant = function() {
        scope.modal = $uibModal.open({
          templateUrl: '/static/template/signup-participant-modal.html',
          scope: scope
        });
      };

      scope.dismissModal = function(reason) {
        scope.modal.dismiss(reason);
        scope.error = null;
      };

      scope.$watch('allSignups', function(allSignups) {
        scope.anyFeedbackPresent = _.some(allSignups, 'feedback.length');
      });

      scope.signUp = function(participant, notes) {
        var payload = {participant_id: participant.id, notes: notes};
        var tripSignup = djangoUrl.reverse('json-leader_participant_signup',
                                           [scope.tripId]);
        $http.post(tripSignup, payload).then(
          function success(response) {
            var signup = response.data.signup;
            formatSignupEmail(signup);
            var destList = response.data.on_trip ? 'onTrip' : 'waitlist';
            scope.signups[destList].push(signup);
            updateSignups();
            updateSignupMemberships();  // Could check just this participant
            scope.dismissModal('success');
          },
          function error(response) {
            scope.error = response.data.message;
          });
      };

      var membershipLapsed = {participant: {membership: {status: "!Active"}}};
      var updateLapsedMembers = function() {
        ['onTrip', 'waitlist'].forEach(function(subList) {
          var lapsedSignups = filterFilter(scope.signups[subList], membershipLapsed);
          scope.lapsedMembers[subList] = _.map(lapsedSignups, 'participant.formattedEmail');
        });
      };

      // So we can use 'updateSignups' as a callback even with truthy first arg
      var updateKeepDeleted = function() {
        updateSignups(false);
      };
      scope.sortableOptions = {stop: updateKeepDeleted,
                               connectWith: '.signup-list'};
      scope.$watch('maximumParticipants', updateKeepDeleted);

      scope.verifyChanges = function() {
        scope.modal = $uibModal.open({
          templateUrl: '/static/template/admin-trip-signups-modal.html',
          scope: scope
        });
      };

      scope.cancel = function() {
        scope.dismissModal('');
        scope.pending = false;
      };

      scope.submit = function() {
        scope.pending = true;
        var signups = scope.allSignups.map(function(signup) {
          return {id: signup.id,
                  deleted: signup.deleted,
                  participant: signup.participant};
        });
        var payload = {signups: signups,
                       maximum_participants: scope.maximumParticipants};
        $http.post(url, payload).then(function() {
          scope.modal.dismiss('success');
          updateSignups(true);  // Remove the deleted signups
          scope.pending = false;
          scope.$emit('tripModified');  // Tell parents that we made changes
        }, function(response) {
          scope.error = response.data.message || "A server error occurred. Please contact the administrator";
          scope.pending = false;
        });
      };
    }
  };
})
.directive('approveTrip', function($http, djangoUrl) {
  return {
    restrict: 'E',
    replace: true,
    scope: {
      tripId: '=',
      approved: '=',
    },
    templateUrl: '/static/template/approve-trip.html',
    link: function (scope, element, attrs) {
      var url = djangoUrl.reverse("json-approve_trip", [scope.tripId]);
      scope.toggleApproval = function(){
        scope.approved = !scope.approved;
        $http.post(url, {approved: scope.approved});
      };
    }
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
      scope.deleteObject = function() {
        if (!scope.apiSlug || !scope.objId) {
          scope.error = "Object unknown; unable to delete";
        }
        $http.post('/' + scope.apiSlug + '/' + scope.objId + '/delete/').then(function() {
          $window.location.href = '/';
        },
        function() {
          scope.error = "An error occurred deleting the object.";
        });
      };

      scope.confirmDelete = function() {
        $uibModal.open({
          templateUrl: '/static/template/delete-modal.html',
          scope: scope
        });
      };
    }
  };
})
.directive('participantLookup', function($window) {
  return {
    restrict: 'E',
    templateUrl: '/static/template/participant-lookup.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.viewParticipant = function(participant) {
        $window.location.href = '/participants/' + participant.id;
      };
    },
  };
})
.directive('participantSelect', function($http, djangoUrl) {
  return {
    restrict: 'E',
    require: '?ngModel',
    scope: {
      msg: '=?',
      name: '@',
      selectedId: '=?',
      selectedName: '@?',
      excludeSelf: '=?'
    },
    templateUrl: '/static/template/participant-select.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.msg = scope.msg || "Search participants...";
      scope.participants = {};

      if (scope.selectedId) {
        scope.participants.selected = {id: scope.selectedId,
                                       name: scope.selectedName};
        ngModelCtrl.$setViewValue(scope.participants.selected);
      }

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
        var queryArgs = {search: search};
        if (scope.excludeSelf) {
          queryArgs.exclude_self = 1;
        }
        $http.get(url, {params: queryArgs}).then(function (response) {
          scope.participants.all = response.data.participants;
        });
      };

      scope.getMatchingParticipants();
    },
  };
})
.directive('flakingParticipants', function($http) {
  return {
    restrict: 'E',
    templateUrl: '/static/template/flaking-participants.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.participants = {flakes: []};

      scope.addFlake = function(participant) {
        if (!_.find(scope.participants.flakes, {id: participant.id})) {
          scope.participants.flakes.push(participant);
        }
        scope.flake = null;
      };

      scope.removeFlake = function(participant) {
        parIndex = _.findIndex(scope.participants.flakes, {id: participant.id});
        if (parIndex !== -1) {
          scope.participants.flakes.splice(parIndex, 1);
        }
      };
    },
  };
})
.directive('leaderSelect', function($http, $q, djangoUrl) {
  return {
    restrict: 'E',
    require: 'ngModel',
    scope: {
      program: '=',
      leaders: '=ngModel',
      leaderIds: '=?',  // Existing IDs, supplied through widget
      name: '@'
    },
    templateUrl: '/static/template/leader-select.html',
    link: function (scope, element, attrs, ngModelCtrl) {
      scope.selected = {
        leaders: [],
      };

      // If leader IDs are passed in, it's an existing trip with an existing program.
      scope.initialProgram = null;

      // A collection of all seen leaders, accessed by ID
      scope.allLeaders = {};

      // Just the leaders who are allowed to lead trips for this particular program
      scope.programLeaders = [];

      // Discard any other unneeded parameters - we only need ID for model, name for display
      var nameAndId = function(par ) {
        return {'id': par.id, 'name': par.name};
      }

      // Start by identifying any existing leaders passed in
      // (This supports editing trips)
      var fetchInitialLeaders = function() {
        if (!scope.leaderIds || !scope.leaderIds.length) {
          return $q.when([]);  // No initial leaders.
        }
        var url = djangoUrl.reverse("json-participants");
        var queryArgs = {'id': scope.leaderIds};

        return $http.get(url, {params: queryArgs}).then(function (response) {
          // Discard unneeded other params
          return response.data.participants.map(nameAndId);
        });
      }

      // Given a new iterable of leader objects, add them to the master mapping
      // (this ensures that the master mapping keeps the same objects)
      var addToLeaderMapping = function(leaders) {
        _.each(leaders, function(leader) {
          if (!_.has(scope.allLeaders, leader.id)) {
            scope.allLeaders[leader.id] = nameAndId(leader);
          }
        });
      };

      var oneTimeInitialFetch = fetchInitialLeaders().then(function(initialLeaders) {
        addToLeaderMapping(initialLeaders);
        scope.selected.leaders = initialLeaders;
        return initialLeaders;
      });

      // Every time the program changes, identify valid leaders
      scope.$watch('program', function identifyValidLeaders(program) {
        if (!program) {
          return;
        }

        // This is the first load of the given program!
        if (scope.leaderIds && scope.initialProgram === null) {
          scope.initialProgram = program;
        }

        $q.all([oneTimeInitialFetch, fetchProgramLeaders()])
          .then(function buildValidLeaders(promises) {
            var initialLeaders = promises[0];
            var programLeaders = promises[1];

            scope.programRatings = {};
            _.each(programLeaders, function(par) {
              scope.programRatings[par.id] = par.rating;
            });

            // Add any previously unseen leaders to our directory
            addToLeaderMapping(programLeaders);

            // Make the programLeaders iterable contain the same objects.
            scope.programLeaders = programLeaders.map(function(par) {
              return scope.allLeaders[par.id];
            });

            var programLeaderIds = _.map(scope.programLeaders, 'id');
            if (program === scope.initialProgram) {
              var noLongerActive = _.filter(initialLeaders, function(par) {
                return !_.includes(programLeaderIds, par.id);
              });
              // Include initial leaders who can no longer lead
              scope.programLeaders = scope.programLeaders.concat(
                _.map(noLongerActive, function(par) {
                  return scope.allLeaders[par.id];
                })
              );
            }

            // Just to be sure that reference integrity is maintained, explicitly translate.
            scope.selected.leaders = _.map(scope.selected.leaders, function(par) {
              return scope.allLeaders[par.id];
            });

            // Now validate that the selected leaders can lead this program
            checkSelectedLeaders();
            ngModelCtrl.$validate();
          });
      });

      /* Fetch all leaders and their ratings for the program. */
      var fetchProgramLeaders = function() {
        var url = djangoUrl.reverse("json-program-leaders", [scope.program]);
        return $http.get(url).then(function (response) {
          return response.data.leaders;
        });
      };

      // (Enable Djangular to display errors on the required validator)
      ngModelCtrl.$isEmpty = function(leaders) {
        return !(leaders && leaders.length);
      };

      // Translate from the model's raw participant IDs to full objects.
      // (maintains proper reference)
      ngModelCtrl.$formatters.push(function(modelValue) {
        return _.map(modelValue, function(leaderId) {
          return scope.allLeaders[leaderId];
        });
      });

      ngModelCtrl.$render = function() {
        scope.selected.leaders = ngModelCtrl.$viewValue;
      };

      /* Annotate all selected leaders with an attribute indicating whether
       * or not they can lead the trip.
       */
      var checkSelectedLeaders = function() {
        var programLeaderIds = _.map(scope.programLeaders, 'id');
        _.each(scope.selected.leaders, function(leader) {
          leader.canLead = _.includes(programLeaderIds, leader.id);
        });
      };

      ngModelCtrl.$validators.leadersOkay = function(modelValue, viewValue) {
        // If we haven't yet checked everybody's ability to lead, do that now.
        viewValue.forEach(function(leader) {
          if (!_.has(leader, 'canLead')) {
            checkSelectedLeaders();
          }
        });

        return _.every(_.map(viewValue, 'canLead'));
      };

      scope.$watch('selected.leaders', function(newValue, oldValue) {
        ngModelCtrl.$setViewValue(scope.selected.leaders);
      });

      ngModelCtrl.$parsers.push(function(viewValue) {
        return _.map(viewValue, 'id');
      });
    }
  };
})
.directive('amountFromAffiliation', function() {
    /* Store the membership amount from the selected affiliation.
     *
     * The form that we submit to CyberSource has two named inputs:
     * - amount (how much to pay, dependent on affiliation)
     * - affiliation (stored in 'merchantDefinedData2')
     *
     * To the user, selecting these two is the same operation. However,
     * to create two form inputs, we need to sneak in another hidden input
     * with the amount to charge.
     *
     * When paying dues as a Participant, this directive is not needed (we can
     * just load a value for `amount` when rendering the form server-side).
     * However, when paying dues as an anonymous participant, this allows
     * us to avoid making the participant make a selection twice.
     */
  return {
    restrict: 'E',
    replace: true,
    scope: {
      affiliation: '=',
      amount: '=',
    },
    //templateUrl: '/static/template/amount-from-affiliation.html',
    template: '<input name="amount" type="hidden" data-ng-value="amount" />',
    link: function (scope, element, attrs) {
      var affiliationToAmount = {
        'MU': 15,
        'MG': 15,
        'NU': 40,
        'NG': 40,
        'MA': 30,
        'ML': 40,
        'NA': 40,
      };

      scope.$watch('affiliation', function(affiliation) {
        scope.amount = affiliationToAmount[affiliation];
      });
    }
  };
});

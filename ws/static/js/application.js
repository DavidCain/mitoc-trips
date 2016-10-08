// TODO: Make a custom AngularUI build with just the templates I need
angular.module('ws', ['ui.bootstrap', 'ui.bootstrap.tpls', 'djng.forms',
                      'ws.ajax', 'ws.auth', 'ws.profile', 'ws.forms', 'ws.lottery', 'ws.stats', 'ws.widgets']);


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
      scope.delayNotice = "<p>If you've already submitted membership dues and/or waiver, " +
                          "our system may take up to 24 hours to mark your membership as active.</p>" +
                          "<p>We're working on a fix for this delay.</p>" +
                          "<p>In the meantime, please feel free to sign up for trips if you believe your membership is active.</p>";
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
      // If signups and leaders are present, we'll use those. Otherwise, fetch from trip.
      tripId: '=?',
    },
    templateUrl: '/static/template/email-trip-members.html',
    link: function (scope, element, attrs) {
      if (scope.tripId && !scope.signups) {
        $http.get(djangoUrl.reverse('json-signups', [scope.tripId]))
          .success(function(data){
            scope.signups = data.signups;
            scope.leaders = data.leaders;
          });
      }

      scope.showEmails = {
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
          var defaultList = scope.signups.onTrip.length ? 'onTrip' : 'leaders';
          scope.showEmails[defaultList] = true;
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

        var emails = scope.showEmails.leaders ? scope.leaders.map(formatEmail) : [];
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
.directive('delete', function($http, $window, $uibModal) {
  return {
    restrict: 'E',
    scope: {
      objId: '=',
      apiSlug: '@',
      label: '@?',
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
})
;

angular.module('ws.stats', [])
.directive('tripsByLeader', function($http, djangoUrl, $window) {
  return {
    restrict: 'E',
    scope: {},
    templateUrl: '/static/template/trips-by-leader.html',
    link: function (scope, element, attrs) {
      // We'll fetch once, then they're available top-level
      var filteredLeaders, allLeaders, allLeadersByPk;

      // Clicking the legend allows optionally hiding activities
      var hiddenActivities = [];

      // Basic chart setup
      var margin = {top: 20, right: 0, bottom: 0, left: 175};
          chartWidth       = 500,
          barHeight        = 20,
          spaceForLegend   = 150,
          chartHeight      = null,  // Will set based on data
          svgHeight        = null,  // Will set based on data
          svgWidth         = margin.left + chartWidth + margin.right + spaceForLegend;

      // 10 colors, selected for qualitative differences (by ColorBrewer)
      // Reordered slightly to give "bolder" colors to common activities
      var colors = [
        '#6a3d9a',
        '#a6cee3',
        '#b2df8a',
        '#33a02c',
        '#e31a1c',
        '#fb9a99',
        '#fdbf6f',
        '#ff7f00',
        '#1f78b4',
        '#cab2d6', // light purple, unused
      ];

      // Specify the chart area and dimensions
      var svg = d3.select(".chart")
          .attr("width", svgWidth)
        .append("g")
          .attr("id", "offset-chart-area")
          .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

      // Create axes (doesn't yet have domain on scales or scale on axes)
      var x = d3.scale.linear().nice();
      var y = d3.scale.ordinal();
      var xAxis = d3.svg.axis()
          .orient("top")
          .tickFormat(d3.format("d"));
      var yAxis = d3.svg.axis()
          .orient("left")
          .tickFormat(function(pk) { return allLeadersByPk[pk].name; })

      var sizeRectange = function(layerBars) {
        return layerBars
          .attr("x", function(d) { return x(d.y0); })  // number of trips per leader, per activity
          .attr("y", function(d) { return y(d.x); })  // Leader's PK
          .attr("width", function(d) {
            return x(d.y + d.y0) - x(d.y0) ;  // Height of difference in prev, new
          });
      };

      // Axis labels (still need to call against axis)
      svg.append("g")
        .attr("class", "axis axis--x");
      svg.append("g")
        .attr("class", "axis axis--y");

      /* Identify all activties represented in data set */
      var getAllActivities = function(leaders) {
        var allTrips = _.flatten(_.map(leaders, 'trips'));  // Will include duplicates
        return _.uniq(_.map(allTrips, 'activity')).sort();
      };

      /* Convert results of 'trips_by_leader' to coords for bar chart layers */
      var toLayers = function(leaders) {
        var noTrips = _.zipObject(allActivities, _.map(allActivities, function() {return []; }));
        var hiddenTrips = _.pick(noTrips, hiddenActivities);

        // Count trips led per leader
        var tripsLed = _.map(leaders, function(leader){
          var groupedTrips = _.groupBy(leader.trips, function(trip){
            return trip.activity;
          });
          return _.extend({pk: leader.pk, name: leader.name}, noTrips, groupedTrips, hiddenTrips);
        });

        // Convert trips led per leader to layers per bar
        var byActivity = allActivities.map(function(activity) {
          return tripsLed.map(function(d) {
            var trips = d[activity];  // Trips of this activity type
            // NOTE: We're going to swap the x and y axis!
            return {x: d.pk, name: d.name, trips: trips, y: trips.length};
          });
        });
        return d3.layout.stack()(byActivity);
      };

      // Create or update the chart of trips by leaders
      // This can be called whenever the underlying data in filteredLeaders changes
      var updateChart = function (disableAnimations) {
        var layers = toLayers(filteredLeaders);

        // Get maximum number of trips by summing the last 'layer' on the bar chart
        var maxNumTrips;  // Max on X
        if (layers.length) {
          maxNumTrips = d3.max(layers[layers.length - 1], function(d) { return d.y0 + d.y; });
        }

        // Update height, since it depends on size of data set
        var chartHeight = barHeight * filteredLeaders.length,
            svgHeight   = margin.top + chartHeight + margin.bottom;  // FIXME: min: legend height

        // Select a margin-offset area within the chart
        var svg = d3.select(".chart")
            .attr("height", svgHeight)
          .select("#offset-chart-area");

        var getLeaderPk = function(d) { return d.x; };

        // Update domain/range and rescale
        x.domain([0, maxNumTrips])
         .rangeRound([0, chartWidth]);
        y.domain(layers[0].map(getLeaderPk))
         .rangeRoundBands([0, chartHeight]);
        xAxis.scale(x);
        yAxis.scale(y);

        // Compare leaders by total number of trips, then by name
        var moreTripsLed = function(leader1, leader2) {
          var selectedActivities = function(leader){
            return _.reject(leader.trips, function(trip) {
              return hiddenActivities.includes(trip.activity);
            }).length;
          };
          tripDiff = selectedActivities(leader2) - selectedActivities(leader1);
          return tripDiff || leader1.name.localeCompare(leader2.name);
        };

        // Create one layer per activity, track on leader pk and activity index
        var layer = svg.selectAll(".layer")
          .data(layers, function(d, i) { return [d.x, i]; });

        layer.enter().append("g")
          .attr("class", "layer")
          .style("fill", function(d, i) { return colors[i]; });

        var layerBars = layer.selectAll("rect")
          .data(function(d) { return d; }, getLeaderPk);
        layerBars.sort(moreTripsLed);

        // Add any new bars, setting height (height won't change again)
        layerBars.enter().append("rect")
            .attr("height", barHeight - 2);  // 2px spacing between bars

        // Adjust the domain to have new sorted leaders
        var leadersByPk = _.keyBy(filteredLeaders, 'pk');
        y.domain(layers[0].map(getLeaderPk).sort(function(pk1, pk2){
          return moreTripsLed(leadersByPk[pk1], leadersByPk[pk2]);
        }));

        // Resize both existing and any new bars (on first load, will already be sorted)
        var animateMs = 500;
        sizeRectange(layerBars.transition().duration(animateMs));
        var ySel = disableAnimations ? svg : svg.transition().duration(animateMs);

        // Axis labels
        svg.select('.axis--x')
          .call(xAxis);
        ySel.select('.axis--y')
          .call(yAxis);

        svg.select('.axis--y')
          .selectAll(".tick")
            .attr("cursor", "pointer")
            .on('click',function(pk){
              var viewParticipantUrl = djangoUrl.reverse("view_participant", [pk]);
              return $window.location.href = viewParticipantUrl;
            });

        layer.exit().remove();
      };

      // After clicking an element in the legend, update which activities are shown
      var updateActivities = function(e) {
        var clickedActivity = this.textContent;

        var hidden = _.includes(hiddenActivities, clickedActivity);
        d3.select(this).style("opacity", hidden ? 1.0 : 0.1);

        if (hidden) {
          hiddenActivities = _.reject(hiddenActivities, function(activity){
            return activity === clickedActivity;
          });
        } else {
          hiddenActivities.push(clickedActivity);
        }

        updateChart();
      };

      // Draw a legend for activities, where each can be clicked to toggle
      var drawLegend = function(activities) {
        var legendRectSize   = 18,
            legendSpacing    = 4,
            gapBetweenGroups = 10;

        var legend = svg.selectAll('.legend')
          .data(activities)
          .enter()
          .append('g')
          .attr('transform', function (d, i) {
              var height = legendRectSize + legendSpacing;
              var offset = -gapBetweenGroups/2;
              var horz = chartWidth + 40 - legendRectSize;
              var vert = i * height - offset;
              return 'translate(' + horz + ',' + vert + ')';
          })
          .attr("cursor", "pointer")
          .on('click', updateActivities);

        legend.append('rect')
          .attr('width', legendRectSize)
          .attr('height', legendRectSize)
          .style('fill', function (d, i) { return colors[i]; })
          .style('stroke', function (d, i) { return colors[i]; });

        legend.append('text')
          .attr('class', 'legend')
          .attr('x', legendRectSize + legendSpacing)
          .attr('y', legendRectSize - legendSpacing)
          .text(function (d) { return d; });

      };

      // Load chart with all leaders
      $http.get(djangoUrl.reverse("trips_by_leader")).then(function (response){
        allLeaders = response.data.leaders;
        allActivities = getAllActivities(allLeaders);
        allLeadersByPk = _.keyBy(allLeaders, 'pk');

        filteredLeaders = allLeaders;
        updateChart(true);

        drawLegend(allActivities);
      });

      // Only show trips occurring after the given date
      var filterByDate = function(leaders, afterDate) {
        return _.map(leaders, function(leader) {
          var newLeader = angular.copy(leader);
          newLeader.trips = _.filter(leader.trips, function(trip){
            return new Date(trip.trip_date) > afterDate;
          });
          return newLeader;
        });
      };

      scope.$watch('startDate', function(afterDate){
        if (afterDate === undefined) {
          return;
        }

        filteredLeaders = filterByDate(allLeaders, afterDate);
        updateChart();
      });
    },
  };
})
;

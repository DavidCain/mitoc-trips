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

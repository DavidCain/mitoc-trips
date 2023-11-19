from django import template

register = template.Library()


@register.inclusion_tag("for_templatetags/trip_rental_table.html")
def trip_rental_table(trip, leader_on_trip, items_by_par, show_serial=False):
    """Display a table of all items rented by participants."""

    # Enforce items are only those rented before the trip itself
    # (Items rented by participants _after_ the trip has ended were not for the trip)
    items_by_par = [
        (participant, [item for item in items if item.checkedout <= trip.trip_date])
        for participant, items in items_by_par
    ]

    return {
        "trip": trip,
        "leader_on_trip": leader_on_trip,
        "items_by_par": items_by_par,  # List of tuples: (Participant, items)
        "show_serial": show_serial,
    }

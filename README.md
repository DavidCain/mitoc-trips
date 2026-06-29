[![Build Status](https://github.com/DavidCain/mitoc-trips/actions/workflows/ci.yml/badge.svg)](https://github.com/DavidCain/mitoc-trips/actions)
[![Code Coverage](https://codecov.io/gh/DavidCain/mitoc-trips/branch/master/graph/badge.svg)](https://codecov.io/gh/DavidCain/mitoc-trips)

# About
This is a Django-based trip management system for the [MIT Outing Club][mitoc].

MITOC's volunteer leaders craft trips to take participants climbing, hiking,
biking, skiing, mountaineering, rafting, canoeing, and surfing. Trips are open
to everyone in the club - a community of thousands.


# Development

There are a number of ways to approach local development, and none of the
suggested steps are strictly required. The key moving parts are:

1. A Postgres server
2. Astral's `uv` managing Python & a virtualenv
3. Node for management of the frontend

Homebrew & asdf are just suggested ways to manage dependencies for local dev.

## Docker

First, install Docker, Docker Compose, and either Docker Desktop or Colima.
If you use Homebrew:
```
brew install docker docker-compose colima
colima start
```

Then start the database & web server:

```bash
docker compose up --build --watch
```

http://localhost:8000/ will then have a running webserver.
You can access the Postgres database directly:

```bash
docker exec -it mitoc-trips-db-1 psql -U ws ws
```

## Local development

You don't have to use Docker - all development can take place directly on your
localhost if desired:

```bash
brew bundle install
direnv allow # (Don't just trust me - inspect .envrc)
export PATH="${$HOME}/.asdf/shims:$PATH"  # (Also add to your rcfiles)
asdf install
npm install
uv run manage.py migrate
make run
```

# Screenshots
## Profile page
![Profile page][screenshots-profile]

## Account management
![Email address management][screenshots-email_address_management]

## Leader application
![Submitted application][screenshots-leader_application_submitted]

## Pending applications
![Activity chairs can review applications][screenshots-leader_application_queue]

## Reviewing applications
![Application under review][screenshots-leader_application]

## Trip view
![An activity chair's view of a trip][screenshots-trip_activity_chair]

## Administering a trip
![Trip administration view][screenshots-trip_admin]

## Adding a participant
![Participant being added to a trip][screenshots-trip_add_participant]

## Interactive leaderboard
![Interactive D3-based widget showing active leaders][screenshots-leaderboard]

## Help pages
![Help pages guide users][screenshots-help]


# [History][about]
This site was created in 2014 to improve MITOC's Winter School program. It has
since evolved into the central portal for all MITOC trips.

Once upon a time, Winter School trips operated on a first-come, first-serve
basis. Signups opened at noon, and filled up extremely quickly. Many
participants found themselves unable to attend any trips in a given weekend,
and others struggled to gain exposure to new activities.

We introduced a lottery system to combat the "fastest gun in the West" problem.
Instead of rewarding trip slots to whomever could sign up the fastest, we used
an equitable algorithm to distribute trip slots. As a result of this new
algorithm, we saw unprecedented levels of participation. Everyone who expressed
interest in attending weekend trips was placed on a trip, and popular
activities like ice climbing were more accessible.

Today, all MITOC trips are organized through this portal. Many trips are
first-come, first-serve, but we use lottery-based signups for other popular
trip formats once subject to same problems as Winter School.


  [mitoc]: https://mitoc.mit.edu
  [about]: https://mitoc-trips.mit.edu/help/about/
  [mitoc-ansible]: https://github.com/DavidCain/mitoc-ansible

  [screenshots-profile]: https://dcain.me/static/images/mitoc-trips/profile.png
  [screenshots-email_address_management]: https://dcain.me/static/images/mitoc-trips/email_address_management.png
  [screenshots-leader_application_submitted]: https://dcain.me/static/images/mitoc-trips/leader_application_submitted.png
  [screenshots-leader_application_queue]: https://dcain.me/static/images/mitoc-trips/leader_application_queue.png
  [screenshots-leader_application]: https://dcain.me/static/images/mitoc-trips/leader_application.png
  [screenshots-trip_activity_chair]: https://dcain.me/static/images/mitoc-trips/trip_activity_chair.png
  [screenshots-trip_admin]: https://dcain.me/static/images/mitoc-trips/trip_admin.png
  [screenshots-trip_add_participant]: https://dcain.me/static/images/mitoc-trips/trip_add_participant.png
  [screenshots-leaderboard]: https://dcain.me/static/images/mitoc-trips/leaderboard.png
  [screenshots-help]: https://dcain.me/static/images/mitoc-trips/help.png

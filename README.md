# About
This Django project supports MITOC's [Winter School][ws], providing a unified
system for participants, leaders, and administrators.

## Background
Every January, the MIT Outing Club ([MITOC][mitoc]) runs a program known as
Winter School. The program is designed to familiarize members of the community
with the outdoors and teach the specific skills required to enjoy various
winter activities. Lectures are held during the week, and some fifty volunteers
lead trips in the White Mountains each weekend.

Every year, approximately 600 people participate in Winter School. 

## System overview
Leaders create trips, which participants may immediately browse. After trip
signups open, participants select trips they're interested in and rank their
choices. A lottery algorithm places participants on trips, adding those who
don't make it on a trip to a waiting list. Participant information (including
any relevant medical information) is passed to trip leaders, and emergency
contact information is passed to the WIMP (an individual tasked with ensuring
the safety of all participants).

Outside of this primary flow, members of the Winter Safety Committee have the
ability to approve trips, manage leadership ratings, and mark mandatory
participation in lectures.


## Design considerations
The system was written with security and usability in mind. Key design features:

- Dynamic, personalized interface
    - Authenticated users have access to various controls
      based on the permissions assosciated with their user account.
    - Page elements are selectively served depending on trip and/or user status.
    - Personalized content allows easier use for leaders and participants.
- User assistance
    - Extensive help pages cover various uses of the system.
    - Individualized messages are automatically generated to guide
      participants, leaders, and administrators.
    - Administrators and safety committee members can easily perform
      administrative actions with a graphical interface
- Responsive
    - A [responsive site layout][responsive] combines with [responsive
      tables][footable] to express information effectively across a
      range of different screen sizes.


# Dependencies
(see `requirements.txt`)

- [Django][django] v. 1.8
- [`django-allauth`][allauth]
- [`django-localflavor`][localflavor]


# Deployment
This project will eventually be cleaved into Winter School-related models
and logic, and a more general-purpose trip signup system. Until then, if you're
interested in running this system yourself, it's quite straightforward to run
the project locally, or (if you're MIT-affiliated) on [Scripts][scripts].

## Deploying locally
This project is designed to be rapidly deployed on a local system for testing.
A SQLite database removes the need for a SQL server and Django's console-based
email backend removes the need for an SMTP server.

The default settings (`conf/local_settings.py`) contain everything you need to
get up and running on your own machine. After installing the required
dependencies, simply run `./manage.py migrate` to initialize the database, then
`./manage.py runserver` to get your project up and running. Navigate to
[http://localhost:8000](http://localhost:8000), and you're ready to tinker!


## Deploying on scripts.mit.edu

### Configuration
Begin by modifying `conf/production_settings_template.py` to match your locker
and access information. First, set a `SECRET_KEY` (default: `None`).

You'll want to change the `NAME` field of `DATABASES`, perhaps specify a path
to your `.cnf` file, and modify any settings designed for the `mitoc` locker.
Change `settings.py` to include settings from `production_settings.py` (or
whatever you named this new configuration file).

Be sure to modify the appropriate `Site` object:

    UPDATE django_site
    SET domain='mitoc.scripts.mit.edu', name='Winter School'
    WHERE id=1;

### URL Rewriting
Use the simple `.htaccess` file provided with Scripts' default Django install,
which is just the following:

    RewriteEngine On
    RewriteRule ^$ index.fcgi/ [QSA,L]
    RewriteCond %{REQUEST_FILENAME} !-f
    RewriteCond %{REQUEST_FILENAME} !-d
    RewriteRule ^(.*)$ index.fcgi/$1 [QSA,L]

### Satisfying dependencies
At time of writing, Scripts supports Django 1.6.6. Most of this project is 
compatible with Django 1.6, but there are a few backwards-incompatible aspects of
Django 1.7 & 1.8. Namely, we make use of signal handling present in Django >1.7
"apps" and settings configurations only available in Django >1.8.

The solution for using Django 1.8 and this project's accompanying
dependencies is to create a virtual environment.

Create the virtual environment so that it inherits the many packages available
on Scripts:

    virtualenv --system-site-packages

When installing software, pass the `-U` flag to install a package only if its
version is newer than the system-wide version. To install the necessary
dependencies for this project:

    pip install -U -r requirements.txt

### FastCGI
Scripts deploys applications with FastCGI. The script must be modified to load
the virtual environment first, before any imports. For a workable `.fcgi` script,
see `index.fcgi`.

### Static files
Scripts will serve a number of files directly. Just run `collectstatic` to put these files 
in `~/web_scripts/<dirname>/static`.



  [mitoc]: http://web.mit.edu/mitoc/www/
  [django]: https://github.com/django/django
  [allauth]: https://github.com/pennersr/django-allauth
  [localflavor]: https://github.com/django/django-localflavor
  [django_select2]: https://github.com/applegrew/django-select2

  [scripts]: http://scripts.mit.edu
  [ws]: http://mitoc.scripts.mit.edu/ws
  [responsive]: http://cyberchimps.com/responsive-theme/
  [footable]: https://github.com/bradvin/FooTable

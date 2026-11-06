"""The door. One box, one button, and nothing that needs the app behind it.

Deliberately its own page rather than a panel inside the main one. The app's
page is three thousand lines that read settings, list features and poll for
running jobs, and every one of those is a request that a signed-out browser is
not allowed to make - so a login drawn inside it would be a screen built out of
things it cannot ask for.

It is also why there is no framework, no icon font and no shared stylesheet
here: the only two things this page can fetch are itself and the favicon.

The wording is the part worth getting right. A wrong password says so; it does
not say whether a user exists, because there are no users. And it says out loud
that this is http on a home network, because a login box implies a promise about
privacy that plain http does not keep, and letting somebody assume otherwise
would be the dishonest half of putting a lock here at all.
"""

from app import web

# The page is `app/web/login.html`.
LOGIN = web.read("login.html")

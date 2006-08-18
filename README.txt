Copyright (c) 2005-2006, Dennis Kaarsemaker

This program is free software; you can redistribute it and/or modify
it under the terms of version 2 of the GNU General Public License as
published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

The syntax to add a tracker is weird, here are some examples:
@bugtracker add freedesktop bugzilla https://bugs.freedesktop.org Freedesktop
@bugtracker add malone malone https://launchpad.net/malone Malone
@bugtracker add debian debbugs http://bugs.debian.org Debian
@bugtracker add openoffice issuezilla http://www.openoffice.org/issues OpenOffice
@bugtracker add django trac http://code.djangoproject.com/ticket Django
@bugtracker add gaim sourceforge http://sourceforge.net/tracker/?group_id=235&atid=100235 Gaim

In general: @bugtracker add <name> <type> <baseurl> [description]
Bugtracker dialects (types) this plugin understands:
* Bugzilla
* Issuezilla (OpenOffice.org's tjernobyl transformation of bugzilla)
* Malone
* Debbugs (debbugs sucks donkeyballs - please fix debbugs)
* Trac (with not-too-buggered-up templates, it needs to do screenscraping)
* Sourceforge (needs atid and group_id in the url!)

To request a bug report, use this syntax:

bug 123
bug #123
supybot bug 123
bug 123, 4, 5
bug 1, 3 and 89

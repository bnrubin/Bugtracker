Copyright (c) 2005-2007, Dennis Kaarsemaker

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
* WikiForms (see bugs.gnewsense.org for an example)

To request a bug report, use this syntax:

bug 123
bug #123
supybot bug 123
bug 123, 4, 5
bug 1, 3 and 89

To rename a bugtracker:
@bugtracker rename old-name new-name

To change details of a bugtracker, just add it again and it will overwrite the
existing tracker.

The bug snarfing (responding to bug numbers/urls) will only work in channels
where supybot.plugins.bugtracker.bugsnarfer is True.

Automatic reporting of new bugs is also possible for Malone (the launchpad
bugtracker). Enabling this is not a trivial process. First step is to set the
supybot.plugins.bugtracker.reportercache variable to a dir for this purpose. You
also need a mail account that supports the + hack (mail for foo+bar@baz.com is
automatically delivered to foo@baz.com while the Delivered-To: header is set to
foo+bar@baz.com) which is accessible via IMAP. I know this is a rather strong
requirement, but that's the way it works now. Patches to make it work in other
situations are appreciated.

Anyway, once that is all set up you're almost there. Let's assume the
mailaddress is bugreporter@yourdomain.com. Now pick a tag for your bugreports,
e.g. ubuntu (you can set a different tag per channel) and create a launchpad
account with address bugreporter+ubuntu@yourdomain.com. Activate that account
and make sure it gets bugmail for the product(s) you want to monitor.

Now set the supybot.plugins.bugtracker.bugreporter in the channels where bugs
are to be reported to the value of the tag for bugs to be reported there and
watch bugs flowing in.

To prevent old bugs from showing up when they change or a comment is being
added, you can manually fill the cache. Just touch files in the reporters cache
with the following name:

tag_here/malone/NN/MMMM where NN is int(bugid/1000) and MMMM is the bugid.

If your products already have many bugreports, consider doing some
screenscraping with the malone searchpages and sed/awk :)

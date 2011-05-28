Bug information reporting plugin, works with many well-known bugtrackers.

The syntax to add a tracker is weird, here are some examples:
@bugtracker add freedesktop bugzilla https://bugs.freedesktop.org Freedesktop
@bugtracker add launchpad launchpad https://launchpad.net/malone Launchpad
@bugtracker add debian debbugs http://bugs.debian.org Debian
@bugtracker add openoffice issuezilla http://www.openoffice.org/issues OpenOffice
@bugtracker add django trac http://code.djangoproject.com/ticket Django
@bugtracker add gaim sourceforge http://sourceforge.net/tracker/?group_id=235&atid=100235 Gaim

In general: @bugtracker add <name> <type> <baseurl> [description]
Bugtracker dialects (types) this plugin understands:
* Bugzilla
* Issuezilla (OpenOffice.org's tjernobyl transformation of bugzilla)
* Launchpad (Including Ubuntu)
* Debbugs (debbugs sucks donkeyballs - please fix debbugs)
* Trac
* WikiForms (see bugs.gnewsense.org for an example)
* str.php from the CUPS project
* Mantis (http://www.mantisbt.org)

A notable exception is Sourceforge. Unfortunatly, it has no API or data export
feature to output bug information in a well-formed way.

To request a bug report, use this syntax:

bug 123
bug #123
launchpad bug 123
bug 123, 4, 5
bugs 1, 3 and 89

To rename a bugtracker:
@bugtracker rename old-name new-name

To change details of a bugtracker, just add it again and it will overwrite the
existing tracker.

The bug snarfing (responding to bug numbers/urls) will only work in channels
where supybot.plugins.bugtracker.bugsnarfer is True.

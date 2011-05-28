# -*- Encoding: utf-8 -*-
###
# Copyright (c) 2005-2007 Dennis Kaarsemaker
# Copyright (c) 2008-2011 Terence Simpson
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
###

import supybot.conf as conf
import supybot.registry as registry
import supybot.ircutils as ircutils

class Bugtrackers(registry.SpaceSeparatedListOfStrings):
    List = ircutils.IrcSet

def configure(advanced):
    from supybot.questions import expect, something, yn, output

    def anything(prompt, default=None):
        """Because supybot is pure fail"""
        from supybot.questions import expect
        return expect(prompt, [], default=default)

    Bugtracker = conf.registerPlugin('Bugtracker', True)

    def getRepeatdelay():
        output("How many seconds should the bot wait before repeating bug information?")
        repeatdelay = something("Enter a number greater or equal to 0", default=Bugtracker.repeatdelay._default)

        try:
            repeatdelay = int(repeatdelay)
            if repeatdelay < 0:
                raise TypeError
        except TypeError:
            output("%r is an invalid value, it must be an integer greater or equal to 0" % repeatdelay)
            return getRepeatdelay()
        else:
            return repeatdelay

    output("Each of the next 3 questions can be set per-channel with the '@Config channel' command")
    bugSnarfer = yn("Enable detecting bugs numbers and URL in all channels?", default=Bugtracker.bugSnarfer._default)
    cveSnarfer = yn("Enable detecting CVE numbers and URL in all channels?", default=Bugtracker.cveSnarfer._default)
    oopsSnarfer = yn("Enable detecting Launchpad OOPS IDs in all channels?", default=Bugtracker.oopsSnarfer._default)
    if advanced:
        replyNoBugtracker = something("What should the bot reply with when a a user requests information from an unknown bug tracker?", default=Bugtracker.replyNoBugtracker._default)
        snarfTarget = something("What should be the default bug tracker used when one isn't specified?", default=Bugtracker.snarfTarget._default)
        replyWhenNotFound = yn("Should the bot report when a bug is not found?", default=Bugtracker.replyWhenNotFound._default)
        repeatdelay = getRepeatdelay()
    else:
        replyNoBugtracker = Bugtracker.replyNoBugtracker._default
        snarfTarget = Bugtracker.snarfTarget._default
        replyWhenNotFound = Bugtracker.replyWhenNotFound._default
        repeatdelay = Bugtracker.repeatdelay._default

    showassignee = yn("Show the assignee of a bug in the reply?", default=Bugtracker.showassignee._default)
    extended = yn("Show tracker-specific extended infomation?", default=Bugtracker.extended._default)

    Bugtracker.bugSnarfer.setValue(bugSnarfer)
    Bugtracker.cveSnarfer.setValue(cveSnarfer)
    Bugtracker.oopsSnarfer.setValue(oopsSnarfer)
    Bugtracker.replyNoBugtracker.setValue(replyNoBugtracker)
    Bugtracker.snarfTarget.setValue(snarfTarget)
    Bugtracker.replyWhenNotFound.setValue(replyWhenNotFound)
    Bugtracker.repeatdelay.setValue(repeatdelay)
    Bugtracker.showassignee.setValue(showassignee)
    Bugtracker.extended.setValue(extended)

Bugtracker = conf.registerPlugin('Bugtracker')

conf.registerChannelValue(Bugtracker, 'bugSnarfer',
    registry.Boolean(False, """Determines whether the bug snarfer will be
    enabled, such that any Bugtracker URLs and bug ### seen in the channel
    will have their information reported into the channel."""))

conf.registerChannelValue(Bugtracker, 'cveSnarfer',
    registry.Boolean(False, """Determines whether the CVE snarfer will be
    enabled, such that any CVE URLs and CVE-????-???? seen in the channel
    will have their information reported into the channel."""))

conf.registerChannelValue(Bugtracker, 'oopsSnarfer',
    registry.Boolean(False, """Determines whether the OOPS snarfer will be
    enabled, such that any OOPS ### seen in the channel
    will have their information reported into the channel."""))

#conf.registerChannelValue(Bugtracker, 'bugReporter',
#    registry.String('', """Report new bugs (experimental)"""))

conf.registerChannelValue(Bugtracker, 'replyNoBugtracker',
    registry.String('I don\'t have a bugtracker %s.', """Determines the phrase
    to use when notifying the user that there is no information about that
    bugtracker site."""))

conf.registerChannelValue(Bugtracker, 'snarfTarget',
    registry.String('launchpad', """Determines the bugtracker to query when the
    snarf command is triggered"""))

conf.registerGlobalValue(Bugtracker, 'bugtrackers',
    Bugtrackers([], """Determines what bugtrackers will be added to the bot when it starts."""))

conf.registerGlobalValue(Bugtracker, 'replyWhenNotFound',
    registry.Boolean(False, """Whether to send a message when a bug could not be
    found"""))

conf.registerChannelValue(Bugtracker, 'repeatdelay',
    registry.Integer(60, """Number of seconds to wait between repeated bug calls"""))

conf.registerChannelValue(Bugtracker, 'showassignee',
    registry.Boolean(False, """Whether to show the assignee in bug reports"""))

conf.registerChannelValue(Bugtracker, 'extended',
    registry.Boolean(False, "Show optional extneded bug information, specific to trackers"))
    
#conf.registerGlobalValue(Bugtracker, 'reportercache',
#    registry.String('', """Name of the basedir for the bugreporter cache""", private=True))

#conf.registerGlobalValue(Bugtracker, 'imap_server',
#    registry.String('', """IMAP server for bugmail account""",private=True))

#conf.registerGlobalValue(Bugtracker, 'imap_user',
#    registry.String('', """IMAP user for bugmail account""", private=True))

#conf.registerGlobalValue(Bugtracker, 'imap_password',
#    registry.String('', """IMAP password for bugmail account""", private=True))

#conf.registerGlobalValue(Bugtracker, 'imap_ssl',
#    registry.Boolean(False, """Use SSL for imap connections""", private=True))


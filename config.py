# -*- Encoding: utf-8 -*-
###
# Copyright (c) 2005-2007 Dennis Kaarsemaker
# Copyright (c) 2008-2010 Terence Simpson
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
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Bugtracker', True)

Bugtracker = conf.registerPlugin('Bugtracker')

conf.registerChannelValue(Bugtracker, 'bugSnarfer',
    registry.Boolean(False, """Determines whether the bug snarfer will be
    enabled, such that any Bugtracker URLs and bug ### seen in the channel
    will have their information reported into the channel."""))

conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'bugReporter',
    registry.String('', """Report new bugs (experimental)"""))

conf.registerChannelValue(Bugtracker, 'replyNoBugtracker',
    registry.String('I don\'t have a bugtracker %s.', """Determines the phrase
    to use when notifying the user that there is no information about that
    bugtracker site."""))

conf.registerChannelValue(Bugtracker, 'snarfTarget',
    registry.String('', """Determines the bugtracker to query when the
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
    
conf.registerGlobalValue(Bugtracker, 'reportercache',
    registry.String('', """Name of the basedir for the bugreporter cache""", private=True))

conf.registerGlobalValue(Bugtracker, 'imap_server',
    registry.String('', """IMAP server for bugmail account""",private=True))

conf.registerGlobalValue(Bugtracker, 'imap_user',
    registry.String('', """IMAP user for bugmail account""", private=True))

conf.registerGlobalValue(Bugtracker, 'imap_password',
    registry.String('', """IMAP password for bugmail account""", private=True))

conf.registerGlobalValue(Bugtracker, 'imap_ssl',
    registry.Boolean(False, """Use SSL for imap connections""", private=True))


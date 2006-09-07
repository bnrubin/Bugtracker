###
# Copyright (c) 2005,2006 Dennis Kaarsemaker
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

def configure(advanced):
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Bugtracker', True)


Bugtracker = conf.registerPlugin('Bugtracker')

conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'bugSnarfer',
    registry.Boolean(False, """Determines whether the bug snarfer will be
    enabled, such that any Bugtracker URLs and bug ### seen in the channel
    will have their information reported into the channel."""))
conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'bugReporter',
    registry.String('', """Report new bugs (experimental)"""))
conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'bugReporter_closed',
    registry.String('', """Report new bugs (experimental)"""))
conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'replyNoBugtracker',
    registry.String('I don\'t have a bugtracker %s.', """Determines the phrase
    to use when notifying the user that there is no information about that
    bugtracker site."""))
conf.registerChannelValue(conf.supybot.plugins.Bugtracker, 'snarfTarget',
    registry.String('', """Determines the bugtracker to query when the
    snarf command is triggered"""))

class Bugtrackers(registry.SpaceSeparatedListOfStrings):
    List = ircutils.IrcSet
conf.registerGlobalValue(conf.supybot.plugins.Bugtracker, 'bugtrackers',
    Bugtrackers([], """Determines what bugtrackers will be added to the bot when it starts."""))
conf.registerGlobalValue(conf.supybot.plugins.Bugtracker, 'replyWhenNotFound',
    registry.Boolean(False, """Whether to send a message when a bug could not be
    found"""))

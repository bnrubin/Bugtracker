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

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.registry as registry
import supybot.schedule as schedule

import re, os, time
import xml.dom.minidom as minidom
from htmlentitydefs import entitydefs as entities
import email.FeedParser

def registerBugtracker(name, url='', description='', trackertype=''):
    conf.supybot.plugins.Bugtracker.bugtrackers().add(name)
    group       = conf.registerGroup(conf.supybot.plugins.Bugtracker.bugtrackers, name)
    URL         = conf.registerGlobalValue(group, 'url', registry.String(url, ''))
    DESC        = conf.registerGlobalValue(group, 'description', registry.String(description, ''))
    TRACKERTYPE = conf.registerGlobalValue(group, 'trackertype', registry.String(trackertype, ''))
    if url:
        URL.setValue(url)
    if description:
        DESC.setValue(description)
    if trackertype:
        if defined_bugtrackers.has_key(trackertype.lower()):
            TRACKERTYPE.setValue(trackertype.lower())
        else:
            raise BugtrackerError("Unknown trackertype: %s" % trackertype)
            
entre = re.compile('&(\S*?);')
def _getnodetxt(node):
    L = []
    for childnode in node.childNodes:
        if childnode.nodeType == childnode.TEXT_NODE:
            L.append(childnode.data)
    val = ''.join(L)
    if node.hasAttribute('encoding'):
        encoding = node.getAttribute('encoding')
        if encoding == 'base64':
            try:
                val = val.decode('base64')
            except:
                val = 'Cannot convert bug data from base64.'
    while entre.search(val):
        entity = entre.search(val).group(1)
        if entity in entities:
            val = entre.sub(entities[entity], val)
        else:
            val = entre.sub('?', val)
    return val

class BugtrackerError(Exception):
    """A bugtracker error"""
    pass

class BugNotFoundError(Exception):
    """Pity, bug isn't there"""
    pass

class Bugtracker(callbacks.PluginRegexp):
    """Show a link to a bug report with a brief description"""
    threaded = True
    callBefore = ['URL']
    regexps = ['turlSnarfer', 'bugSnarfer', 'oopsSnarfer']

    def __init__(self, irc):
        callbacks.PluginRegexp.__init__(self, irc)
        self.db = ircutils.IrcDict()
        for name in self.registryValue('bugtrackers'):
            registerBugtracker(name)
            group = self.registryValue('bugtrackers.%s' % name.replace('.','\\.'), value=False)
            if group.trackertype() in defined_bugtrackers.keys():
                self.db[name] = defined_bugtrackers[group.trackertype()](name, group.url(), group.description())
            else:
                raise BugtrackerError("Unknown trackertype: %s" % group.trackertype())
        self.shorthand = utils.abbrev(self.db.keys())
        try:
            schedule.removeEvent(self.name())
        except:
            pass
        schedule.addPeriodicEvent(lambda: self.reportnewbugs(irc),  60, name=self.name())
        self.shown = {}
        self.nomailtime = 0

    def is_ok(self, channel, tracker, bug):
        now = time.time()
        for k in self.shown.keys():
            if self.shown[k] < now - 60:
                self.shown.pop(k)
        if (channel, tracker, bug) not in self.shown:
            self.shown[(channel, tracker, bug)] = now
            return True
        return False

    def reportnewbugs(self,irc):
        # Compile list of bugs
        #print "Reporting new bugs"
        tracker = self.db['malone']
        bugs = {}
        fixed = {}
        for c in irc.state.channels:
            dir = self.registryValue('bugReporter', channel=c)
            if not dir:
                continue
            #print "Reporting in %s (%s)" % (c, dir)
            if dir not in bugs:
                #print "Reloading info from %s" % dir
                bugs[dir] = {}
                if dir.endswith('bugmail'):
                    if len(os.listdir(os.path.join(dir,'Maildir','new'))) == 0:
                        self.nomailtime += 1
                        if self.nomailtime == 30:
                            irc.queueMsg(ircmsgs.privmsg(c,'WARNING: No bugmail received in 30 minutes. Please poke Seveas.'))
                            self.nomailtime = 0
                    else:
                        #irc.queueMsg(ircmsgs.privmsg('#ubuntu-bots','Seveas: your lucky number is %d' % self.nomailtime))
                        self.nomailtime = 0
                for file in os.listdir(os.path.join(dir,'Maildir','new')):
                    #print "Checking %s" % file
                    fd = open(os.path.join(dir,'Maildir','new',file))
                    _data = fd.readlines()
                    fd.close()
                    os.unlink(os.path.join(dir,'Maildir','new',file))
                    component = ''
                    data = []
                    for line in _data:
                        if line[0] in ' \t':
                            data[-1] += '%s ' % line.strip()
                        else:
                            data.append('%s ' % line.strip())
                    for line in data:
                        if line.startswith('X-Launchpad-Bug:') and not component:
                            if 'component' in line:
                                component = line[line.find('component=')+10:]
                                component = component[:component.find(';')]
                                if component == 'None':
                                    component = ''
                        if line.startswith('Reply-To:'):
                            #print line
                            try:
                                bug = int(line.split()[2])
                                try:
                                    os.makedirs(os.path.join(dir,str(int(bug/1000))))
                                except:
                                    pass
                                if bug > 58184 and not os.path.exists(os.path.join(dir,str(int(bug/1000)),str(bug))):
                                    #print "New bug: %d" % bug
                                    fd2 = open(os.path.join(dir,str(int(bug/1000)),str(bug)),'w')
                                    fd2.close()
                                    if bug not in bugs[dir]:
                                        try:
                                            if component:
                                                bugs[dir][bug] = self.get_bug(tracker, bug).replace('"','(%s) "' % component, 1)
                                            else:
                                                bugs[dir][bug] = self.get_bug(tracker, bug)
                                        except:
                                            #print "Unable to get bug %d" % b
                                            pass
                            except:
                                #raise
                                pass # Ignore errors. Iz wrong mail
                            break
            #print "New bugs in %s (%s): %s" % (c, dir, str(bugs[dir].keys()))
            # Now show them
            for b in sorted(bugs[dir].keys()):
                irc.queueMsg(ircmsgs.privmsg(c,'New bug: #%s' % bugs[dir][b][bugs[dir][b].find('bug ')+4:]))

    def add(self, irc, msg, args, name, trackertype, url, description):
        """<name> <type> <url> [<description>]

        Add a bugtracker <url> to the list of defined bugtrackers. <type> is the
        type of the tracker (currently only Malone, Debbugs, Bugzilla,
        Issuezilla and Trac are known). <name> is the name that will be used to
        reference the bugzilla in all commands. Unambiguous abbreviations of
        <name> will be accepted also.  <description> is the common name for the
        bugzilla and will be listed with the bugzilla query; if not given, it
        defaults to <name>.
        """
        name = name.lower()
        if not description:
            description = name
        if url[-1] == '/':
            url = url[:-1]
        trackertype = trackertype.lower()
        if trackertype in defined_bugtrackers:
            self.db[name] = defined_bugtrackers[trackertype](name,url,description)
        else:
            irc.error("Bugtrackers of type '%s' are not understood" % trackertype)
            return
        registerBugtracker(name, url, description, trackertype)
        self.shorthand = utils.abbrev(self.db.keys())
        irc.replySuccess()
    add = wrap(add, ['something', 'something', 'url', additional('text')])

    def remove(self, irc, msg, args, name):
        """<abbreviation>

        Remove the bugtracker associated with <abbreviation> from the list of
        defined bugtrackers.
        """
        try:
            name = self.shorthand[name.lower()]
            del self.db[name]
            self.registryValue('bugtrackers').remove(name)
            self.shorthand = utils.abbrev(self.db.keys())
            irc.replySuccess()
        except KeyError:
            s = self.registryValue('replyNoBugtracker', msg.args[0])
            irc.error(s % name)
    remove = wrap(remove, ['text'])

    def list(self, irc,  msg, args, name):
        """[abbreviation]

        List defined bugtrackers. If [abbreviation] is specified, list the
        information for that bugtracker.
        """
        if name:
            name = name.lower()
            try:
                name = self.shorthand[name]
                (url, description, type) = (self.db[name].url, self.db[name].description,
                                            self.db[name].__class__.__name__)
                irc.reply('%s: %s, %s [%s]' % (name, description, url, type))
            except KeyError:
                s = self.registryValue('replyNoBugtracker', msg.args[0])
                irc.error(s % name)
        else:
            if self.db:
                L = self.db.keys()
                L.sort()
                irc.reply(utils.str.commaAndify(L))
            else:
                irc.reply('I have no defined bugtrackers.')
    list = wrap(list, [additional('text')])

    def bugSnarfer(self, irc, msg, match):
        r"""\b(?P<bt>(([a-z]+)?\s+bugs?|[a-z]+))\s+#?(?P<bug>\d+(?!\d*\.\d+)((,|\s*(and|en|et|und|ir))\s*#?\d+(?!\d*\.\d+))*)"""
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        # Don't double on commands
        s = str(msg).split(':')[2]
        if s[0] in str(conf.supybot.reply.whenAddressedBy.chars):
            return
        sure_bug = match.group('bt').endswith('bug') or match.group('bt').endswith('bug')
        # FIXME dig into supybot docs/code
        #if conf.supybot.reply.whenAddressedBy.strings:
        #    for p in conf.supybot.reply.whenAddressedBy.strings:
        #        if s.startswith(str(p)):
        #            return
        # Get tracker name
        bugids = match.group('bug')
        reps = ((' ',''),('#',''),('and',','),('en',','),('et',','),('und',','),('ir',','))
        for r in reps:
            bugids = bugids.replace(r[0],r[1])
        bugids = bugids.split(',')[:5]
        bt = map(lambda x: x.lower(), match.group('bt').split())
        name = ''
        if len(bt) == 1 and not (bt[0] in ['bug','bugs']):
            try:
                name = bt[0].lower()
                tracker = self.db[name]
            except:
                return
        elif len(bt) == 2:
            try:
                name = bt[0].lower()
                tracker = self.db[name]
            except:
                name = ''
                pass
        if not name:
            snarfTarget = self.registryValue('snarfTarget', msg.args[0])
            if not snarfTarget:
                return
            try:
                name = self.shorthand[snarfTarget.lower()]
            except:
               s = self.registryValue('replyNoBugtracker', name)
               irc.error(s % name)
        try:
            tracker = self.db[name]
        except KeyError:
            s = self.registryValue('replyNoBugtracker', name)
            irc.error(s % name)
        else:
            for bugid in bugids:
                bugid = int(bugid)
                if not self.is_ok(msg.args[0],tracker, bugid):
                    continue
                try:
                    report = self.get_bug(tracker,bugid)
                except BugtrackerError, e:
                    if 'private' in str(e):
                        irc.reply("Bug %d on http://launchpad.net/bugs/%d is private" % (bugid, bugid))
                        return
                    if not sure_bug and bugid < 30:
                        return
                    irc.error(str(e))
                else:
                    irc.reply(report, prefixNick=False)

    #show_bug.cgi?id=|bugreport.cgi?bug=|(bugs|+bug)/|ticket/|tracker/.*aid=
    #&group_id=\d+&at_id=\d+
    def turlSnarfer(self, irc, msg, match):
        "(?P<tracker>https?://.*?)(show_bug.cgi\?id=|bugreport.cgi\?bug=|(bugs|\+bug)/|/ticket/|tracker/.*aid=)(?P<bug>\d+)(?P<sfurl>&group_id=\d+&at_id=\d+)?"
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        try:
            tracker = self.get_tracker(match.group(0),match.group('sfurl'))
            if not tracker:
                return
            if not self.is_ok(msg.args[0],tracker, int(match.group('bug'))):
                return
            report = self.get_bug(tracker,int(match.group('bug')), do_url = False)
        except BugtrackerError, e:
            irc.error(str(e))
        else:
            irc.reply(report, prefixNick=False)
    turlSnarfer = urlSnarfer(turlSnarfer)

    # Only useful for launchpad developers
    def oopsSnarfer(self, irc, msg, match):
        r"OOPS-(?P<oopsid>\d*[A-Z]\d+)"
        oopsid = match.group(1)
        irc.reply("https://devpad.canonical.com/~jamesh/oops.cgi/%s" % oopsid, prefixNick=False)

    def get_tracker(self,snarfurl,sfdata):
        snarfhost = snarfurl.replace('http://','').replace('https://','')
        if '/' in snarfurl:
            snarfhost = snarfhost[:snarfhost.index('/')]
        for t in self.db.keys():
            tracker = self.db[t]
            url = tracker.url.replace('http://','').replace('https://','')
            if 'sourceforge.net' in url:
                # Try to find the correct sf tracker
                if str(sfdata) in tracker.url:
                    return tracker
            if '/' in url:
                url = url[:url.index('/')]
            if url in snarfhost:
                return tracker
        if 'sourceforge.net' in snarfurl:
            return self.db['sourceforge']
        # No tracker found, bummer. Let's try and add one
        if 'show_bug.cgi' in snarfurl:
            tracker = Bugzilla().get_tracker(snarfurl)
            if tracker:
                self.db[tracker.name] = tracker
                self.shorthand = utils.abbrev(self.db.keys())
                return tracker
        return None

    def get_bug(self, tracker, id, do_url = True):
        (product, title, severity, status, url) = tracker.get_bug(id)
        severity = severity[0].upper() + severity[1:].lower()
        status = status[0].upper() + status[1:].lower()
        if not do_url:
            url = ''
        if product:
            return "%s bug %s in %s \"%s\" [%s,%s] %s" % (tracker.description, id, product, 
                                                          title, severity, status, url)
        return "%s bug %s \"%s\" [%s,%s] %s" % (tracker.description, id, title, severity, status, url)

# Define all bugtrackers
class IBugtracker:
    def __init__(self, name=None, url=None, description=None):
        self.name        = name
        self.url         = url
        self.description = description

    def get_bug(self, id):
        raise BugTrackerError("Bugtracker class does not implement get_bug")

    def get_tracker(self, url):
        raise BugTrackerError("Bugtracker class does not implement get_tracker")

class Bugzilla(IBugtracker):
    def get_tracker(self, url):
        url = url.replace('show_bug','xml')
        try:
            bugxml = utils.web.getUrl(url)
            tree = minidom.parseString(bugxml)
            url  = str(tree.getElementsByTagName('bugzilla')[0].attributes['urlbase'].childNodes[0].data)
            if url[-1] == '/':
                url = url[:-1]
            name = url[url.find('//') + 2:]
            if '/' in name:
                name = name[:name.find('/')]
            desc = name
            registerBugtracker(name, url, desc, 'bugzilla')
            tracker = Bugzilla(name, url, desc)
            return tracker
        except:
            return None
    def get_bug(self, id):
        url = "%s/xml.cgi?id=%d" % (self.url,id)
        try:
            bugxml = utils.web.getUrl(url)
            zilladom = minidom.parseString(bugxml)
        except Exception, e:
            s = 'Could not parse XML returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        bug_n = zilladom.getElementsByTagName('bug')[0]
        if bug_n.hasAttribute('error'):
            errtxt = bug_n.getAttribute('error')
            s = 'Error getting %s bug #%s: %s' % (self.description, id, errtxt)
            raise BugtrackerError, s
        try:
            title = _getnodetxt(bug_n.getElementsByTagName('short_desc')[0])
            status = _getnodetxt(bug_n.getElementsByTagName('bug_status')[0])
            try:
                status += ": " + _getnodetxt(bug_n.getElementsByTagName('resolution')[0])
            except:
                pass
            component = _getnodetxt(bug_n.getElementsByTagName('component')[0])
            severity = _getnodetxt(bug_n.getElementsByTagName('bug_severity')[0])
        except Exception, e:
            s = 'Could not parse XML returned by %s bugzilla: %s' % (self.description, e)
            raise BugtrackerError, s
        return (component, title, severity, status, "%s/show_bug.cgi?id=%d" % (self.url, id))

class Issuezilla(IBugtracker):
    def get_bug(self, id):
        url = "%s/xml.cgi?id=%d" % (self.url,id)
        try:
            bugxml = utils.web.getUrl(url)
            zilladom = minidom.parseString(bugxml)
        except Exception, e:
            s = 'Could not parse XML returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        bug_n = zilladom.getElementsByTagName('issue')[0]
        if not (bug_n.getAttribute('status_code') == '200'):
            s = 'Error getting %s bug #%s: %s' % (self.description, id, bug_n.getAttribute('status_message'))
            raise BugtrackerError, s
        try:
            title = _getnodetxt(bug_n.getElementsByTagName('short_desc')[0])
            status = _getnodetxt(bug_n.getElementsByTagName('issue_status')[0])
            try:
                status += ": " + _getnodetxt(bug_n.getElementsByTagName('resolution')[0])
            except:
                pass
            component = _getnodetxt(bug_n.getElementsByTagName('component')[0])
            severity = _getnodetxt(bug_n.getElementsByTagName('issue_type')[0])
        except Exception, e:
            s = 'Could not parse XML returned by %s bugzilla: %s' % (self.description, e)
            raise BugtrackerError, s
        return (component, title, severity, status, "%s/show_bug.cgi?id=%d" % (self.url, id))

class Malone(IBugtracker):
    def _parse(self, task):
        parser = email.FeedParser.FeedParser()
        parser.feed(task)
        return parser.close()
    def _sort(self, task1, task2):
        # Status sort: 
        try:
            statuses   = ['Rejected', 'Fix Released', 'Fix Committed', 'Unconfirmed', 'Needs Info', 'In Progress', 'Confirmed']
            severities = ['Undecided', 'Wishlist', 'Minor', 'Low', 'Normal', 'Medium', 'Major', 'High', 'Critical']
            if task1['status'] not in statuses and task2['status'] in statuses: return 1
            if task1['status'] in statuses and task2['status'] not in statuses: return -1
            if task1['importance'] not in severities and task2['importance'] in severities: return 1
            if task1['importance'] in severities and task2['importance'] not in severities: return -1
            if not (task1['status'] == task2['status']):
                if statuses.index(task1['status']) < statuses.index(task2['status']):
                    return -1
                return 1
            if not (task1['importance'] == task2['importance']):
                if severities.index(task1['importance']) < severities.index(task2['importance']):
                    return -1
                return 1
        except: # Launchpad changed again?
            return 0
        return 0
    def get_bug(self, id):
        try:
            bugdata = utils.web.getUrl("%s/%d/+text" % (self.url,id))
        except Exception, e:
            if '404' in str(e):
                s = 'Error getting %s bug #%s: Bug does not exist' % (self.description, id)
                raise BugtrackerError, s
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        summary = {}
        # Trap private bugs
        if "<!-- 4a. didn't try to log in last time: -->" in bugdata:
            raise BugtrackerError, "This bug is private"
        try:
            # Split bug data into separate pieces (bug data, task data)
            data     =  bugdata.split('\n\n')
            bugdata  = data[0]
            taskdata = data[1:]
            parser   = email.FeedParser.FeedParser()
            parser.feed(bugdata)
            bugdata = parser.close()
            taskdata = map(self._parse, taskdata)
            taskdata.sort(self._sort)
            taskdata = taskdata[-1]
                
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        t = taskdata['task']
        if '(' in t:
            t = t[:t.rfind('(') -1]
        return (t, bugdata['title'], taskdata['importance'], 
                taskdata['status'], "%s/bugs/%s" % (self.url.replace('/malone',''), id))
            
# <rant>
# Debbugs sucks donkeyballs
# * HTML pages are inconsistent
# * Parsing mboxes gets incorrect with cloning perversions (eg with bug 330000)
# * No sane way of accessing bug reports in a machine readable way (bts2ldap
#   has no search on bugid)
# * The damn thing allow incomplete bugs, eg bugs without severity set. WTF?!?
#
# So sometimes the plugin will return incorrect things - so what. Fix the
# damn bts before complaining.
# There's a patch against the thing since august 2003 for enabling machine
# readable output: http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=207225
#
# It's not only releases that go slow in Debian, apparently the bugtracker
# development is even slower than that...
# </rant>
class Debbugs(IBugtracker):
    def parse_mail(self, id, text, data):
        (headers, text) = text.split("\n\n", 1)
        for h in headers.split("\n"):
            h2 = h.lower()
            if h2.startswith('to') and ('%d-close' % id in h2 or '%d-done' % id in h2):
                data['status'] = 'Closed'
            if data['title'] == 'unknown' and h2.startswith('subject'):
                data['title'] = h[8:].strip()
    
        infirstmail = False
        for l in text.split("\n"):
            l2 = l.lower().split()
            if len(l2) == 0:
                if infirstmail: return
                continue
            if l2[0] in ['quit', 'stop', 'thank', '--']:
                return
            elif l2[0] == 'package:':
                data['package'] = l2[1]
                infirstmail = True
            elif l2[0] == 'severity:':
                data['severity'] = l2[1]
            try:
                if len(l2) > 1:
                    if l2[0] in ['reassign', 'reopen', 'retitle', 'severity'] and not (int(l2[1]) == id):
                        continue
            except ValueError: # Parsing to int failed, so not an integer
                if l2[0] == 'reassign':
                    data['package'] = l2[2]
                elif l2[0] == 'reopen':
                    data['status'] = 'Open'
                elif l2[0] == 'retitle':
                    data['title'] = l.split(None,2)[2]
                elif l2[0] == 'severity':
                    data['severity'] = ls[2]
                
    def get_bug(self, id):
        url = "%s/cgi-bin/bugreport.cgi?bug=%d;mbox=yes" % (self.url,id)
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        if '<p>There is no record of Bug' in bugdata:
            raise BugtrackerError, "%s bug %d does not exist" % (self.description, id)
        try:
            data = {'package': 'unknown','title': 'unknown','severity':'unknown','status':'Open'}
            for m in bugdata.split("\n\n\nFrom"):
                self.parse_mail(id, m, data)
        except Exception, e:
            s = 'Could not parse data returned by %s bugtracker: %s' % (self.description, e)
            raise BugtrackerError, s
        return (data['package'], data['title'], data['severity'], data['status'], "%s/%s" % (self.url, id))

# For trac based trackers we also need to do some screenscraping - should be
# doable unless a certain track instance uses weird templates.
class Trac(IBugtracker):
    def get_bug(self, id):
        url = "%s/%d" % (self.url, id)
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        for l in bugdata.split("\n"):
            if '<h1>Ticket' in l:
                severity = l[l.find('(')+1:l.find(')')]
            if 'class="summary"' in l:
                title = l[l.find('>')+1:l.find('</')]
            if 'class="status"' in l:
                status = l[l.find('<strong>')+8:l.find('</strong>')]
            if 'headers="h_component"' in l:
                package = l[l.find('>')+1:l.find('</')]
            if 'headers="h_severity"' in l:
                severity = l[l.find('>')+1:l.find('</')]
        return (package, title, severity, status, "%s/%s" % (self.url, id))
        
class WikiForms(IBugtracker):
    def get_bug(self, id):
        def strip_tags(s):
            while '<' in s and '>' in s:
                s = str(s[:s.find('<')]) + str(s[s.find('>')+1:])
            return s

        url = "%s/%05d" % (self.url, id)
        #print url
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        for l in bugdata.split("\n"):
            l2 = l.lower()
            if '<dt>importance</dt>' in l2:
                severity = 'Importance ' + strip_tags(l[l.find('<dd>')+4:])
            if '<dt>summary</dt>' in l2:
                title = strip_tags(l[l.find('<dd>')+4:])
            if '<dt>status</dt>' in l2:
                status = strip_tags(l[l.find('<dd>')+4:])
            if '<dt>category</dt>' in l2:
                package = strip_tags(l[l.find('<dd>')+4:])
        return (package, title, severity, status, "%s/%05d" % (self.url, id))

sfre = re.compile(r"""
                  .*?
                  <h2>\[.*?\]\s*(?P<title>.*?)</h2>
                  .*?
                  Priority.*?(?P<priority>\d+)
                  .*?
                  Status.*?<br>\s+(?P<status>\S+)
                  .*?
                  Resolution.*?<br>\s+(?P<resolution>\S+)
                  .*?
                  """, re.VERBOSE | re.DOTALL | re.I)

class Sourceforge(IBugtracker):
    _sf_url = 'http://sf.net/support/tracker.php?aid=%d'
    def get_bug(self, id):
        url = self._sf_url % id
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        try:
            reo = sfre.search(bugdata)
            status = reo.group('status')
            resolution = reo.group('resolution')
            if not (resolution.lower() == 'none'):
                status += ' ' + resolution
            return (None, reo.group('title'), "Pri: %s" % reo.group('priority'), status, self._sf_url % id)
        except:
            raise BugtrackerError, "Bug not found"

# Introspection is quite cool
defined_bugtrackers = {}
v = vars()
for k in v.keys():
    if type(v[k]) == type(IBugtracker) and issubclass(v[k], IBugtracker) and not (v[k] == IBugtracker):
        defined_bugtrackers[k.lower()] = v[k]

# Let's add a few bugtrackers by default
registerBugtracker('mozilla', 'http://bugzilla.mozilla.org', 'Mozilla', 'bugzilla')
registerBugtracker('ubuntu', 'http://bugzilla.ubuntu.com', 'Ubuntu', 'bugzilla')
registerBugtracker('gnome', 'http://bugzilla.gnome.org', 'Gnome', 'bugzilla')
registerBugtracker('gnome2', 'http://bugs.gnome.org', 'Gnome', 'bugzilla')
registerBugtracker('kde', 'http://bugs.kde.org', 'KDE', 'bugzilla')
registerBugtracker('ximian', 'http://bugzilla.ximian.com', 'Ximian', 'bugzilla')
registerBugtracker('freedesktop', 'http://bugzilla.freedesktop.org', 'Freedesktop', 'bugzilla')
registerBugtracker('freedesktop2', 'http://bugs.freedesktop.org', 'Freedesktop', 'bugzilla')
# Given that there is only one, let's add it by default
registerBugtracker('openoffice', 'http://openoffice.org/issues', 'OpenOffice.org', 'issuezilla')
# Given that there is only one, let's add it by default
registerBugtracker('malone', 'http://launchpad.net/malone', 'Malone', 'malone')
# Given that there is only one, let's add it by default
registerBugtracker('debian', 'http://bugs.debian.org', 'Debian', 'debbugs')
# Let's add a few bugtrackers by default
registerBugtracker('trac', 'http://projects.edgewall.com/trac/ticket', 'Trac', 'trac')
registerBugtracker('django', 'http://code.djangoproject.com/ticket', 'Django', 'trac')
# Let's add a few bugtrackers by default
registerBugtracker('supybot', 'http://sourceforge.net/tracker/?group_id=58965&atid=489447', 'Supybot', 'sourceforge')
# Special one, do NOT disable/delete
registerBugtracker('sourceforge', 'http://sourceforge.net/tracker/', 'Sourceforge', 'sourceforge')

Class = Bugtracker

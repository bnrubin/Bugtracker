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

from supybot.commands import *
import supybot.utils as utils
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.registry as registry
import supybot.schedule as schedule
import supybot.log as supylog

import re, os, time, imaplib, commands
import xml.dom.minidom as minidom
from htmlentitydefs import entitydefs as entities
import email.FeedParser
import SOAPpy

bad_words = ["fuck","fuk","fucking","fuking","fukin","fuckin","fucked","fuked","fucker","shit","cunt","bastard","nazi","nigger","nigga","cock","bitches","bitch"]

def makeClean(s):
    words = s.split()
    for word in words:
        if word.lower() in bad_words:
            words[words.index(word)] = "<censored>"
    return " ".join(words)

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

cvere = re.compile(r'<th.*?Description.*?<td.*?>(.*?)\s*</td>', re.I | re.DOTALL)
class Bugtracker(callbacks.PluginRegexp):
    """Show a link to a bug report with a brief description"""
    threaded = True
    callBefore = ['URL']
    regexps = ['turlSnarfer', 'bugSnarfer', 'oopsSnarfer', 'cveSnarfer']

    def __init__(self, irc):
        callbacks.PluginRegexp.__init__(self, irc)
        self.db = ircutils.IrcDict()
        events = []
        for name in self.registryValue('bugtrackers'):
            registerBugtracker(name)
            group = self.registryValue('bugtrackers.%s' % name.replace('.','\\.'), value=False)
            if group.trackertype() in defined_bugtrackers.keys():
                self.db[name] = defined_bugtrackers[group.trackertype()](name, group.url(), group.description())
            else:
#                raise BugtrackerError("Unknown trackertype: %s (%s)" % (group.trackertype(), name))
                self.log.warning("Bugtracker: Unknown trackertype: %s (%s)" % (group.trackertype(), name))
        self.shorthand = utils.abbrev(self.db.keys())

        # Schedule bug reporting
        self.shown = {}
        if self.registryValue('imap_server') and self.registryValue('reportercache'):
            try:
                schedule.removeEvent(self.name() + '.bugreporter')
            except:
                pass
            schedule.addPeriodicEvent(lambda: self.reportnewbugs(irc),  60, name=self.name() + '.bugreporter')
            self.events += [self.name() + '.bugreporter']
            self.log.info('Bugtracker: Adding scheduled event "%s.bugreporter"' % self.name())

    def die(self):
        try:
           for event in self.events:
                self.log.info('Bugtracker: Removing scheduled event "%s"' % event)
                schedule.removeEvent(event)
                schedule.removeEvent(self.name())
        except:
            pass

    def is_ok(self, channel, tracker, bug):
        now = time.time()
        for k in self.shown.keys():
            if self.shown[k] < now - self.registryValue('repeatdelay', channel):
                self.shown.pop(k)
        if (channel, tracker, bug) not in self.shown:
            self.shown[(channel, tracker, bug)] = now
            return True
        return False

    def is_new(self, tracker, tag, id):
        bugreporter_base = self.registryValue('reportercache')
        if not os.path.exists(os.path.join(bugreporter_base,tag,tracker.name,str(int(id/1000)),str(id))):
            try:
                os.makedirs(os.path.join(bugreporter_base,tag,tracker.name,str(int(id/1000))))
            except:
                pass
            fd = open(os.path.join(bugreporter_base,tag,tracker.name,str(int(id/1000)),str(id)),'w')
            fd.close()
            return True
        return False

    def reportnewbugs(self,irc):
        # Compile list of bugs
        self.log.info("Bugtracker: Checking for new bugs")
        bugs = {}
        if self.registryValue('imap_ssl'):
            sc = imaplib.IMAP4_SSL(self.registryValue('imap_server'))
        else:
            sc = imaplib.IMAP4(self.registryValue('imap_server'))
        sc.login(self.registryValue('imap_user'), self.registryValue('imap_password'))
        sc.select('INBOX')
        new_mail = sc.search(None, '(UNSEEN)')[1][0].split()[:20]

        # Read all new mail
        for m in new_mail:
            msg = sc.fetch(m, 'RFC822')[1][0][1]
            fp = email.FeedParser.FeedParser()
            sc.store(m, '+FLAGS', "(\Deleted)") # Mark message deleted so we don't have to process it again
            fp.feed(msg)
            bug = fp.close()
            tag = None

            if 'X-Launchpad-Bug' not in bug.keys():
                self.log.info('Bugtracker: Ignoring e-mail with no detectable bug (Not from Launchpad)')            
                continue
            else:
                tag = bug['X-Launchpad-Bug']
                if 'distribution=' not in tag and 'product=' not in tag:
                    self.log.info('Bugtracker: Ignoring e-mail with no detectable bug (no distro/product)')
                    continue
                else:
                    tag = tag.split(';')[0].strip().replace("product=",'').replace("distribution=","")

            if not tag:
                self.log.info('Bugtracker: Ignoring e-mail with no detectible bug (bad tag)')
                
            tag = tag[tag.find('+')+1:tag.find('@')]
            if tag not in bugs:
                bugs[tag] = {}

            # Determine bugtracker type (currently only Launchpad is supported anyway)
            if bug['X-Launchpad-Bug']:
                tracker = self.db['launchpad']
                id = int(bug['Reply-To'].split()[1])
                subj = bug['Subject'];
                if '[NEW]' not in subj: #Not a new bug
                    continue
                if self.is_new(tracker, tag, id):
                    component = bug['X-Launchpad-Bug']
                    if 'component' in component:
                        component = component[component.find('component=')+10:]
                        component = component[:component.find(';')].replace('None','')
                    else:
                        component = ''
                    try:
                        if component:
                            bugs[tag][id] = self.get_bug('',tracker, id, False)[0].replace('"','(%s) "' % component, 1)
                        else:
                            bugs[tag][id] = self.get_bug('',tracker, id, False)[0]
                        if '[apport]' in bugs[tag][id]:
                            bugs[tag].pop(id)
                    except:
                        self.log.info("Bugtracker: Unable to get new bug %d" % id)
                        pass
            else:
                self.log.info('Bugtracker: Ignoring e-mail with no detectable bug')

        reported_bugs = 0

        for c in irc.state.channels:
            tags = self.registryValue('bugReporter', channel=c)
            if not tags:
                continue
            for tag in tags.split(','):
                if not tag or tag not in bugs.keys():
                    continue
                for b in sorted(bugs[tag].keys()):
                    irc.queueMsg(ircmsgs.privmsg(c,'New bug: #%s' % bugs[tag][b][bugs[tag][b].find('bug ')+4:]))
                    reported_bugs = reported_bugs+1

    def add(self, irc, msg, args, name, trackertype, url, description):
        """<name> <type> <url> [<description>]

        Add a bugtracker <url> to the list of defined bugtrackers. <type> is the
        type of the tracker (currently only Launchpad, Debbugs, Bugzilla,
        Issuezilla, Mantis and Trac are known). <name> is the name that will be used to
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
    add = wrap(add, [('checkCapability', 'admin'), 'something', 'something', 'url', additional('text')])

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
    remove = wrap(remove, [('checkCapability', 'admin'), 'text'])

    def rename(self, irc, msg, args, oldname, newname, newdesc):
        """<oldname> <newname>

        Rename the bugtracker associated with <oldname> to <newname>.
        """
        try:
            name = self.shorthand[oldname.lower()]
            group = self.registryValue('bugtrackers.%s' % name.replace('.','\\.'), value=False)
            d = group.description()
            if newdesc:
                d = newdesc
            self.db[newname] = defined_bugtrackers[group.trackertype()](name,group.url(),d)
            registerBugtracker(newname, group.url(), d, group.trackertype())
            del self.db[name]
            self.registryValue('bugtrackers').remove(name)
            self.shorthand = utils.abbrev(self.db.keys())
            irc.replySuccess()
        except KeyError:
            s = self.registryValue('replyNoBugtracker', msg.args[0])
            irc.error(s % name)
    rename = wrap(rename, [('checkCapability', 'admin'), 'something','something', additional('text')])

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
        r"""\b(?P<bt>(([a-z0-9]+)?\s+bugs?|[a-z0-9]+):?)\s+#?(?P<bug>\d+(?!\d*[\-\.]\d+)((,|\s*(and|en|et|und|ir))\s*#?\d+(?!\d*[\-\.]\d+))*)"""
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        nbugs = msg.tagged('nbugs')
        if not nbugs: nbugs = 0
        if nbugs >= 5:
            return

        # Don't double on commands
        s = str(msg).split(':')[2]
        if s and s[0] in str(conf.supybot.reply.whenAddressedBy.chars):
            return
        sure_bug = match.group('bt').endswith('bug') or match.group('bt').endswith('bug')
        
        # Get tracker name
        bugids = match.group('bug')
        reps = ((' ',''),('#',''),('and',','),('en',','),('et',','),('und',','),('ir',','))
        for r in reps:
            bugids = bugids.replace(r[0],r[1])
        bugids = bugids.split(',')[:5-nbugs]
        if not sure_bug:
            bugids = [x for x in bugids if int(x) > 100]
        msg.tag('nbugs', nbugs + len(bugids))
        bt = map(lambda x: x.lower(), match.group('bt').split())
        # Strip off trailing ':' from the tracker name. Allows for (LP: #nnnnnn)
        if len(bt) and bt[0].endswith(':'):
            bt[0] = bt[:-1]
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
            snarfTarget = self.registryValue('snarfTarget', msg.args[0]).lower()
            if not snarfTarget:
                self.log.warning("Bugtracker: no snarfTarget for Bugtracker")
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
                try:
                    report = self.get_bug(msg.args[0],tracker,bugid,self.registryValue('showassignee', msg.args[0]))
                except BugNotFoundError:
                    if self.registryValue('replyWhenNotFound'):
                        irc.error("%s bug %d could not be found" % (tracker.description, bugid))
                except BugtrackerError, e:
                    if 'private' in str(e):
                        irc.reply("Bug %d on http://launchpad.net/bugs/%d is private" % (bugid, bugid))
                        return
                    if not sure_bug and bugid < 30:
                        return
                    irc.error(str(e))
                else:
                    for r in report:
                        irc.reply(makeClean(r), prefixNick=False)

    def turlSnarfer(self, irc, msg, match):
        r"(?P<tracker>https?://\S*?)/(Bugs/0*|str.php\?L|show_bug.cgi\?id=|bugreport.cgi\?bug=|(bugs|\+bug)/|ticket/|tracker/|\S*aid=)(?P<bug>\d+)(?P<sfurl>&group_id=\d+&at_id=\d+)?"
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        nbugs = msg.tagged('nbugs')
        if not nbugs: nbugs = 0
        if nbugs >= 5:
            return
        msg.tag('nbugs', nbugs+1)
        try:
            tracker = self.get_tracker(match.group(0),match.group('sfurl'))
            if not tracker:
                return
            report = self.get_bug(msg.args[0],tracker,int(match.group('bug')),self.registryValue('showassignee', msg.args[0]), do_url = False)
        except BugtrackerError, e:
            irc.error(str(e))
        except BugNotFoundError, e:
            irc.error("%s bug %s not found" % (tracker, match.group('bug')))
        else:
            for r in report:
                irc.reply(makeClean(r), prefixNick=False)
    turlSnarfer = urlSnarfer(turlSnarfer)

    # Only useful for launchpad developers
    def oopsSnarfer(self, irc, msg, match):
        r"OOPS-(?P<oopsid>\d*[\dA-Z]+)"
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        oopsid = match.group(1)
        if oopsid.lower() == "tools":
            return
        irc.reply("https://lp-oops.canonical.com/oops.py/?oopsid=%s" % oopsid, prefixNick=False)
        #irc.reply("https://devpad.canonical.com/~jamesh/oops.cgi/%s" % oopsid, prefixNick=False)

    def cveSnarfer(self, irc, msg, match):
        r"(cve[- ]\d{4}[- ]\d{4})"
        if msg.args[0][0] == '#' and not self.registryValue('bugSnarfer', msg.args[0]):
            return
        cve = match.group(1).replace(' ','-').upper()
        url = 'http://cve.mitre.org/cgi-bin/cvename.cgi?name=%s' % cve
        cvedata = utils.web.getUrl(url)
        m = cvere.search(cvedata)
        if m:
            cve = m.group(1).replace('\n', ' ')
            irc.reply("%s (%s)" % (cve,url))

    def cveUrlSnarfer(self, irc, msg, match):
        pass

    def get_tracker(self,snarfurl,sfdata):
        snarfurl = snarfurl.replace('sf.net','sourceforge.net')
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

    def get_bug(self, channel, tracker, id, do_assignee, do_url = True):
        reports = []
        for r in tracker.get_bug(id):
            if not self.is_ok(channel, tracker, r[0]):
                continue
            showext = self.registryValue('extended', channel)
            extinfo = ''
            if len(r) == 8:
                (bid, product, title, severity, status, assignee, url, extinfo) = r
            else:
                (bid, product, title, severity, status, assignee, url) = r

            severity = severity[0].upper() + severity[1:].lower()
            status = status[0].upper() + status[1:].lower()
            if not do_url:
                url = ''
            if product:
                if showext:
                    reports.append("%s bug %s in %s \"%s\" %s [%s,%s] %s" % (tracker.description, bid, product, 
                                                                          title, extinfo, severity, status, url))
                else:
                    reports.append("%s bug %s in %s \"%s\" [%s,%s] %s" % (tracker.description, bid, product, 
                                                                          title, severity, status, url))
            else:
                if showext:
                    reports.append("%s bug %s \"%s\" %s [%s,%s] %s" % (tracker.description, bid, title, extinfo, severity, status, url))
                else:
                    reports.append("%s bug %s \"%s\" [%s,%s] %s" % (tracker.description, bid, title, severity, status, url))
            if do_assignee and assignee:
                reports[-1] = reports[-1] + (" - Assigned to %s" % assignee)
        return reports

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
            s = 'Could not parse XML returned by %s: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        bug_n = zilladom.getElementsByTagName('bug')[0]
        if bug_n.hasAttribute('error'):
            errtxt = bug_n.getAttribute('error')
            if errtxt == 'NotFound':
                raise BugNotFoundError
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
            assignee = '(unavailable)'
            try:
                assignee = _getnodetxt(bug_n.getElementsByTagName('assigned_to')[0])
            except:
                pass
        except Exception, e:
            s = 'Could not parse XML returned by %s bugzilla: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        return [(id, component, title, severity, status, assignee, "%s/show_bug.cgi?id=%d" % (self.url, id))]

class Issuezilla(IBugtracker):
    def get_bug(self, id):
        url = "%s/xml.cgi?id=%d" % (self.url,id)
        try:
            bugxml = utils.web.getUrl(url)
            zilladom = minidom.parseString(bugxml)
        except Exception, e:
            s = 'Could not parse XML returned by %s: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        bug_n = zilladom.getElementsByTagName('issue')[0]
        if not (bug_n.getAttribute('status_code') == '200'):
            if bug_n.getAttribute('status_message') == 'NotFound':
                raise BugNotFoundError
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
            assignee = _getnodetxt(bug_n.getElementsByTagName('assigned_to')[0])
        except Exception, e:
            s = 'Could not parse XML returned by %s bugzilla: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        return [(id, component, title, severity, status, assignee, "%s/show_bug.cgi?id=%d" % (self.url, id))]

class Launchpad(IBugtracker):
    def __init__(self, *args, **kwargs):
        IBugtracker.__init__(self, *args, **kwargs)
        self.lp = None

        # A word to the wise:
        # The Launchpad API is much better than the /+text interface we currently use,
        # it's faster and easier to get the information we need.
        # The current /+text interface is not really maintained by Launchpad and most,
        # or all, of the Launchpad developers hate it. For this reason, we are dropping
        # support for /+text in the future in favour of launchpadlib.
        # Terence Simpson (tsimpson) 2010-04-20

        try: # Attempt to use launchpadlib, python bindings for the Launchpad API
            from launchpadlib.launchpad import Launchpad
            from launchpadlib.uris import LPNET_SERVICE_ROOT
            cachedir = os.path.join(conf.supybot.directories.data.tmp(), 'lpcache')
            if hasattr(Launchpad, 'login_anonymously'):
                self.lp = Launchpad.login_anonymously("Ubuntu Bots - Bugtracker", LPNET_SERVICE_ROOT, cachedir)
            else:
                self.lp = Launchpad.login("Ubuntu Bots - Bugtracker", '', '', LPNET_SERVICE_ROOT, cahedir)
        except ImportError:
            # Ask for launchpadlib to be installed
            supylog.warning("Please install python-launchpadlib, the old interface is deprecated")
        except Exception: # Something unexpected happened
            self.lp = None
            supylog.error("Error accessing Launchpad API")

    def _parse(self, task):
        parser = email.FeedParser.FeedParser()
        parser.feed(task)
        return parser.close()
    def _sort(self, task1, task2):
        # Status sort: 
        try:
            statuses = ["Unknown", "Invalid", "Won't Fix", "Fix Released", "Fix Committed", "New", "Incomplete", "Confirmed", "Triaged", "In Progress"]
            severities = ["Unknown", "Undecided", "Wishlist", "Low", "Medium", "High", "Critical"]
            if task1['status'] not in statuses and task2['status'] in statuses: return -1
            if task1['status'] in statuses and task2['status'] not in statuses: return 1
            if task1['importance'] not in severities and task2['importance'] in severities: return -1
            if task1['importance'] in severities and task2['importance'] not in severities: return 1
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
        if self.lp:
            return self.get_bug_new(id)
        return self.get_bug_old(id)

    def get_bug_new(self, id):
        def _sort(task1, task2):
            statuses = ["Unknown", "Invalid", "Won't Fix", "Fix Released", "Fix Committed", "New", "Incomplete", "Confirmed", "Triaged", "In Progress"]
            severities = ["Unknown", "Undecided", "Wishlist", "Low", "Medium", "High", "Critical"]
            task1_status = task1.status
            task1_importance = task1.importance
            task2_status = task2.status
            task2_importance = task2.importance
            if task1_status != task2_status:
                if statuses.index(task1_status) < statuses.index(task2_status):
                    return -1
                return 1
            if task1_importance != task2_importance:
                if severities.index(task1_importance) < severities.index(task2_importance):
                    return -1
                return 1
            return 0

        try:
            bugdata = self.lp.bugs[id]
            if bugdata.private:
                raise BugtrackerError, "This bug is private"
            dup = bugdata.duplicate_of
            affected = bugdata.users_affected_count_with_dupes
            heat = bugdata.heat
            tasks = bugdata.bug_tasks

            if tasks.total_size != 1:
                tasks = list(tasks)
                tasks.sort(_sort)
                taskdata = tasks[-1]
            else:
                taskdata = tasks[0]

            assignee = taskdata.assignee
            t = taskdata.bug_target_display_name #task name

            if assignee: # "Diaplay Name (Launchpad ID)"
                assignee = u"%s (%s)" % (assignee.display_name, assignee.name)
            else:
                assignee = ''

        except Exception, e:
            supylog.exception("Error gathering bug data for %s bug %d" % (self.description, id))
            s = 'Could not parse data returned by %s: %s (%s/bugs/%d)' % (self.description, e, self.url, id)
            raise BugtrackerError, s

        extinfo = "(affected: %d, heat: %d)" % (affected, heat)

        if dup:
            dupbug = self.get_bug(dup.id)
            return [(id, t, bugdata.title + (' (dup-of: %d)' % dup.id), taskdata.importance,
                    taskdata.status, assignee, "%s/bugs/%s" % (self.url, id))] + dupbug
        return [(id, t, bugdata.title, taskdata.importance, taskdata.status,
                assignee, "%s/bugs/%s" % (self.url, id), extinfo)]

    def get_bug_old(self, id):
        if id == 1:
            raise BugtrackerError, "https://bugs.launchpad.net/ubuntu/+bug/1 (Not reporting large bug)"

        try:
            bugdata = utils.web.getUrl("%s/bugs/%d/+text" % (self.url,id))
        except Exception, e:
            if '404' in str(e):
                raise BugNotFoundError
            s = 'Could not parse data returned by %s: %s (%s/bugs/%d)' % (self.description, e, self.url, id)
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
            s = 'Could not parse data returned by %s: %s (%s/bugs/%d)' % (self.description, e, self.url, id)
            raise BugtrackerError, s
        # Try and find duplicates
        t = taskdata['task']
        if '(' in t:
            t = t[:t.rfind('(') -1]
        if bugdata['duplicate-of']:
            dupbug = self.get_bug(int(bugdata['duplicate-of']))
            return [(id, t, bugdata['title'] + (' (dup-of: %d)' % dupbug[0][0]), taskdata['importance'], 
                    taskdata['status'], taskdata['assignee'], "%s/bugs/%s" % (self.url, id))] + dupbug
        return [(id, t, bugdata['title'], taskdata['importance'], 
                taskdata['status'], taskdata['assignee'], "%s/bugs/%s" % (self.url, id))]
            
# <rant>
# Debbugs sucks donkeyballs
# * HTML pages are inconsistent
# * Parsing mboxes gets incorrect with cloning perversions (eg with bug 330000)
# * No sane way of accessing bug reports in a machine readable way (bts2ldap
#   has no search on bugid)
# * The damn thing allow incomplete bugs, eg bugs without severity set. WTF?!?
#
# Fortunately bugs.donarmstrong.com has a SOAP interface which we can use.
# </rant>
class Debbugs(IBugtracker):
    def __init__(self, *args, **kwargs):
        IBugtracker.__init__(self, *args, **kwargs)
        self.soap_proxy = SOAPpy.SOAPProxy("bugs.debian.org/cgi-bin/soap.cgi", "Debbugs/SOAP/Status")
        self.soap_proxy.soapaction = "Debbugs/SOAP/Status#get_status"

    def get_bug(self, id):
        bug_url = "http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=%d" % id
        try:
            raw = self.soap_proxy.get_status(id)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s' % (self.description, e)
            raise BugtrackerError, s
        if not raw:
            raise BugNotFoundError
        raw = raw['item']['value']
        try:
            if len(raw['fixed_versions']):
                status = 'Fixed'
            else:
                status = 'Open'
            return [(id, raw['package'], raw['subject'], raw['severity'], status, '', "%s/%s" % (self.url, id))]
        except Exception, e:
            s = 'Could not parse data returned by %s bugtracker: %s (%s)' % (self.description, e, bug_url)
            raise BugtrackerError, s

class Mantis(IBugtracker):
    def __init__(self, *args, **kwargs):
        IBugtracker.__init__(self, *args, **kwargs)
        self.soap_proxy = SOAPpy.SOAPProxy(self.url + "/api/soap/mantisconnect.php", "http://futureware.biz/mantisconnect")
        self.soap_proxy.soapaction = "http://futureware.biz/mantisconnect#mc_issue_get"

    def get_bug(self, id):
        url = self.url + "/view.php?id=%i" % id
        try:
            raw = self.soap_proxy.mc_issue_get('', "", id)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        if not raw:
            raise BugNotFoundError
        try:
            return [(id, raw['project']['name'], raw['summary'], raw['priority']['name'], raw['resolution']['name'], '', url)]
        except Exception, e:
            s = 'Could not parse data returned by %s bugtracker: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s

# For trac based trackers we get the tab-separated-values format.
# The other option is a comma-separated-values format, but if the description
# has commas, things get tricky.
# This should be more robust than the screen-scraping done previously.
class Trac(IBugtracker):
    def get_bug(self, id): # This is still a little rough, but it works :)
        bug_url = "%s/%d" % (self.url, id)
        try:
            raw = utils.web.getUrl("%s?format=tab" % bug_url)
        except Exception, e:
            if 'HTTP Error 500' in str(e):
                raise BugNotFoundError
            s = 'Could not parse data returned by %s: %s' % (self.description, e, bug_url)
            raise BugtrackerError, s
        raw = raw.replace("\r\n", '\n')
        (headers, rest) = raw.split('\n', 1)
        headers = headers.strip().split('\t')
        rest = rest.strip().split('\t')
        title = status = package = severity = assignee = "Unknown"
        if "summary" in headers:
            title = rest[headers.index("summary")]
        if "status" in headers:
            status = rest[headers.index("status")]
        if "component" in headers:
            package = rest[headers.index("component")]
        if "severity" in headers:
            severity = rest[headers.index("severity")]
        if "owner" in headers:
            assingee = rest[headers.index("owner")]
        if severity == "Unknown" and "priority" in headers:
            severity = rest[headers.index("priority")]

        return [(id, package, title, severity, status, assignee, bug_url)]
        
class WikiForms(IBugtracker):
    def get_bug(self, id):
        def strip_tags(s):
            while '<' in s and '>' in s:
                s = str(s[:s.find('<')]) + str(s[s.find('>')+1:])
            return s

        url = "%s/%05d" % (self.url, id)
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            if 'HTTP Error 404' in str(e):
                raise BugNotFoundError
            s = 'Could not parse data returned by %s: %s (%s)' % (self.description, e, url)
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
        return [(id, package, title, severity, status, '', "%s/%05d" % (self.url, id))]

class Str(IBugtracker):
    def get_bug(self, id):
        def strip_tags(s):
            while '<' in s and '>' in s:
                s = str(s[:s.find('<')]) + str(s[s.find('>')+1:])
            return s
        url = "%s?L%d" % (self.url, id)
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        for l in bugdata.split("\n"):
            l2 = l.lower()
            if 'nowrap>priority:</th>' in l2:
                severity = 'Priority ' + l[l.find(' - ')+3:min(l.find(','),l.find('</td>'))]
            if '>application:</th>' in l2:
                package = l[l.find('<td>')+4:l.find('</td>')]
            if 'nowrap>status:</th>' in l2:
                status = l[l.find(' - ')+3:l.find('</td>')]
            if 'nowrap>summary:</th>' in l2:
                title = l[l.find('<td>')+4:l.find('</td>')]
            if 'nowrap>assigned to:</th>' in l2:
                assignee = strip_tags(l[l.find('<td>')+4:l.find('</td>')])
                if assignee == 'Unassigned':
                    assignee = 'nobody'
        return [(id, package, title, severity, status, assignee, "%s?L%d" % (self.url, id))]
        

sfre = re.compile(r"""
                  .*?
                  <h2>\[.*?\]\s*(?P<title>.*?)</h2>
                  .*?
                  assigned.*?<br>\s+(?P<assignee>\S+)
                  .*?
                  priority.*?(?P<priority>\d+)
                  .*?
                  status.*?<br>\s+(?P<status>\S+)
                  .*?
                  resolution.*?<br>\s+(?P<resolution>\S+)
                  .*?
                  """, re.VERBOSE | re.DOTALL | re.I)
class Sourceforge(IBugtracker):
    _sf_url = 'http://sf.net/support/tracker.php?aid=%d'
    def get_bug(self, id):
        url = self._sf_url % id
        try:
            bugdata = utils.web.getUrl(url)
        except Exception, e:
            s = 'Could not parse data returned by %s: %s (%s)' % (self.description, e, url)
            raise BugtrackerError, s
        try:
            reo = sfre.search(bugdata)
            status = reo.group('status')
            resolution = reo.group('resolution')
            if not (resolution.lower() == 'none'):
                status += ' ' + resolution
            return [(id, None, reo.group('title'), "Pri: %s" % reo.group('priority'), status, reo.group('assignee'),self._sf_url % id)]
        except:
            raise BugNotFoundError

# Introspection is quite cool
defined_bugtrackers = {}
v = vars()
for k in v.keys():
    if type(v[k]) == type(IBugtracker) and issubclass(v[k], IBugtracker) and not (v[k] == IBugtracker):
        defined_bugtrackers[k.lower()] = v[k]

registerBugtracker('mozilla', 'http://bugzilla.mozilla.org', 'Mozilla', 'bugzilla')
#registerBugtracker('ubuntu', 'http://bugzilla.ubuntu.com', 'Ubuntu', 'bugzilla')
registerBugtracker('ubuntu', 'https://launchpad.net', 'Ubuntu', 'launchpad')
registerBugtracker('gnome', 'http://bugzilla.gnome.org', 'Gnome', 'bugzilla')
registerBugtracker('gnome2', 'http://bugs.gnome.org', 'Gnome', 'bugzilla')
registerBugtracker('kde', 'http://bugs.kde.org', 'KDE', 'bugzilla')
registerBugtracker('ximian', 'http://bugzilla.ximian.com', 'Ximian', 'bugzilla')
registerBugtracker('freedesktop', 'http://bugzilla.freedesktop.org', 'Freedesktop', 'bugzilla')
registerBugtracker('freedesktop2', 'http://bugs.freedesktop.org', 'Freedesktop', 'bugzilla')
registerBugtracker('openoffice', 'http://openoffice.org/issues', 'OpenOffice.org', 'issuezilla')
registerBugtracker('launchpad', 'https://launchpad.net', 'Launchpad', 'launchpad')
registerBugtracker('lp', 'https://launchpad.net', 'Launchpad', 'launchpad')
registerBugtracker('malone', 'https://launchpad.net', 'Launchpad', 'launchpad')
registerBugtracker('debian', 'http://bugs.debian.org', 'Debian', 'debbugs')
registerBugtracker('trac', 'http://trac.edgewall.org/ticket', 'Trac', 'trac')
registerBugtracker('django', 'http://code.djangoproject.com/ticket', 'Django', 'trac')
registerBugtracker('cups', 'http://www.cups.org/str.php', 'CUPS', 'str')
registerBugtracker('gnewsense', 'http://bugs.gnewsense.org/Bugs', 'gNewSense', 'wikiforms')
registerBugtracker('supybot', 'http://sourceforge.net/tracker/?group_id=58965&atid=489447', 'Supybot', 'sourceforge')
registerBugtracker('mantis', "http://www.mantisbt.org/bugs", "Mantis", 'mantis')
# Don't delete this one
registerBugtracker('sourceforge', 'http://sourceforge.net/tracker/', 'Sourceforge', 'sourceforge')
Class = Bugtracker

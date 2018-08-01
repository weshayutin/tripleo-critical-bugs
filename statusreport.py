# The MIT License (MIT)
# Copyright (c) 2017 Wes Hayutin <weshayutin@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import ConfigParser

from datetime import date
from datetime import datetime
from dateutil.parser import parse
import os

from reports.launchpad import LaunchpadReport
import reports.trello as trello
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText


class StatusReport(object):

    def __init__(self, config, args):
        self.config = config
        self.args = args
        self.brief_status = {}
        self.detailed_status = {}



    def summarise_launchpad_bugs(self):
        if not self.config.has_section('LaunchpadBugs'):
            return

        bugs = self._get_config_items('LaunchpadBugs')

        report = LaunchpadReport(bugs, self.config)
        bugs_with_alerts_open, bugs_with_alerts_closed  = report.generate()
        return bugs_with_alerts_open, bugs_with_alerts_closed


    def print_report(self, bug_list):
        bug_number_list = []
        for k, v in bug_list.iteritems():
            print k
            bug_number_list.append(str(k))
        return bug_number_list


    def _get_config_items(self, section_name, prefix=None):
        if not self.config.has_section(section_name):
            return {}

        items = {k: v for (k, v) in self.config.items(section_name)
                 if not k.startswith('_') and (prefix is None or k.startswith(prefix))}
        return items

    def compare_bugs_with_cards(self, list_of_bugs, cards):
        open_bugs = list_of_bugs
        cards_outtage_names = []
        for card in cards:
            cards_outtage_names.append(card['name'])
            print(card['name'].encode('utf-8'))

        #debug only
        #open_bugs = ['1704849']

        match = []
        for card in cards_outtage_names:
            #print "card " + card
            for key in open_bugs:
                #print "key " + str(key)
                key = str(key)
                if key in card:
                    match.append(int(key))
        print "##########################################"
        print "openbugs " + str(set(open_bugs))
        print "match " + str(set(match))
        critical_bugs_with_out_escalation_cards = list(set(open_bugs) - set(match))
        return critical_bugs_with_out_escalation_cards

    def create_escalation(self, config, critical_bugs_with_out_escalation_cards, list_of_bugs, trello_list):
        if not critical_bugs_with_out_escalation_cards:
            print "There are no bugs that require a new escalation"
        else:
            # send email to list
            for bug in critical_bugs_with_out_escalation_cards:
                bug_title = list_of_bugs[bug].title
                bug = str(bug)
                fromaddr = config.get('Email', 'from')
                toaddr = config.get('Email', 'to')
                msg = MIMEMultipart()
                msg['From'] = fromaddr
                msg['To'] = toaddr
                msg['Subject'] = "[CIX][LP:" + bug + "][tripleoci][proa] " + bug_title
                body = "Automatically generated escalation via #tripleo alerts: https://bugs.launchpad.net/tripleo/+bug/" + bug
                body += "\n\nEscalation cards can be found in the New / Triage column of https://trello.com/b/j4IcIomh/production-chain-escalation"
                msg.attach(MIMEText(body, 'plain'))
                text = msg.as_string()

                server = smtplib.SMTP(config.get('Email', 'smtp_server'), config.get('Email', 'smtp_port'))
                # server.sendmail(fromaddr, toaddr, text)
                # print "escalation email sent to " + toaddr + " subj:" + msg['Subject']
                server.quit()

                # create escalation card
                trello_api_context = trello.ApiContext(config)
                trello_cards = trello.Cards(trello_api_context)
                trello_cards.create(msg['Subject'], trello_list)


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("files", metavar="FILE",  nargs='+', help="Configuration Files")

    args = arg_parser.parse_args()

    for config_file in args.files:
        # Load config file
        config = ConfigParser.SafeConfigParser()
        # Preserve Case in keys
        config.optionxform = str
        if not os.path.exists(config_file):
            raise ValueError('Failed to open/read "{file}"'.format(file=config_file))
        config.read(config_file)

        report = StatusReport(config, args)

        bugs_with_alerts_open, bugs_with_alerts_closed = report.summarise_launchpad_bugs()

        print "*** open critical bugs ***"
        open_bugs = report.print_report(bugs_with_alerts_open)
        print "*** closed critical bugs ***"
        report.print_report(bugs_with_alerts_closed)

        trello_api_context = trello.ApiContext(config)
        trello_boards = trello.Boards(trello_api_context)

        trello_new_list = trello_boards.get_lists_by_name(config.get('TrelloConfig', 'board_id'),
                                        config.get('TrelloConfig', 'list_new'))
        trello_new_list_id = str(trello_new_list[0]['id'])

        all_cards_on_board = trello_boards.get_cards(config.get('TrelloConfig', 'board_id'))
        print "all cards " + str(len(all_cards_on_board))
        cards_outtage = all_cards_on_board

        critical_bugs_with_out_escalation_cards = report.compare_bugs_with_cards(bugs_with_alerts_open, cards_outtage )
        print "critical bugs not tracked on board " + str(critical_bugs_with_out_escalation_cards)

        report.create_escalation(config, critical_bugs_with_out_escalation_cards, bugs_with_alerts_open, trello_new_list_id)


if __name__ == '__main__':
    main()

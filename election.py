import pandas as pd
import time
import sys
import socket
import toml
import gspread
import os
import json
import random

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from googleapiclient.discovery import build
from email.message import EmailMessage
import base64
import parse


SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LEN_VOTER_ID = 32
LEN_SURVEY_ID = 8

QUORUM_TIME_LIMIT = 86400


class OnlineVote:
    VOTE_TYPES = ["selective", "referendum", "2/3 referendum"]

    def __init__(self, config_file="config.toml"):
        self.config = None
        self.logs = []

        self.df = None
        self.votes = None

        self.gc = None
        self.sh = None
        self.worksheet = None
        self.creds = None

        self.email = None
        self.password = None

        self.log("Election created!")
        self.set_config(config_file)

    def log(self, s):
        """
        Logs string to stdout and log output which will be included in results email.
        """
        out = time.strftime("[%Y-%m-%d %H:%M:%S]: ", time.localtime())
        print(out + str(s))
        self.logs.append(out + str(s))

    def exit(self, code):
        """
        Exits the program upon completion or error.
        """
        self.log("Program exited with code {}".format(code))
        with open(
            time.strftime("logs/%Y-%m-%d_%H%M_logs.txt", time.localtime()), "w"
        ) as o:
            o.write("\n".join(self.logs))
            o.write("\n")

        if code == -2:
            self.email_tampering()
        if code == -1:
            if self.df is not None:
                with open("voter_ids.txt", "w") as f:
                    f.write("\n".join(list(self.df["voter_ids"])))

        sys.exit(code)

    def check_internet(self, host="8.8.8.8", port=53, timeout=1, log=False):
        """
        Checks for internet access. Exits if no internet.

        Args:
            host (str): host to attempt to ping. By default uses Google's public
                DNS
            port (int): port to use in connection. By default uses port 53
            timeout (int): time to wait for response
        """
        try:
            if log:
                self.log("Pinging host...")
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                (host, port)
            )
            if log:
                self.log("Verified internet connection")
        except socket.error as e:
            self.log("{}: {}".format(e.__class__.__name__, str(e)))
            self.exit(-1)

    def set_voters(self, file):
        """
        Fetches voter names and email addresses from a csv formatted file
        or a Google Sheets location.
        """
        try:
            self.log("Fetching voter emails...")
            if "https://docs.google.com/spreadsheets" in file:
                self.gc = gspread.oauth(
                    credentials_filename="oauth.json",
                    authorized_user_filename="authorized_user.json",
                )
                sh = self.gc.open_by_url(self.config["voters_file"])
                worksheet = sh.worksheet(self.config["voters_sheet"])

                raw = self.retry(worksheet.get_values)

                self.df = pd.DataFrame(
                    data=raw[1:],
                    columns=["first_name", "nickname", "last_name", "email"],
                )
            else:
                self.df = pd.read_csv(
                    file,
                    names=["first_name", "nickname", "last_name", "email"],
                    header=0,
                )
        except Exception as e:
            self.log("{}: {}".format(e.__class__.__name__, str(e)))
            self.exit(-1)

    def confirm_voters(self):
        """
        Prompts the user running the election to confirm the list of eligible
        voters. Exits if list is not confirmed.
        """
        self.log("List of voters participating:")
        self.log("\n" + self.df.to_string())

        confirm = input("Does this list of voters look correct? [y/n]: ")
        if confirm == "y" or confirm == "Y":
            self.log("List of voters confirmed by election official")
        else:
            self.log("List of voters denied by election official")
            self.exit(-1)

    def generate_voter_ids(self):
        """
        Generates unique voter IDs for each eligible voter, as well as a
        survey ID.
        """
        voter_ids = []
        used_ids = set()
        for _ in range(len(self.df)):
            random.seed(time.time())
            n = random.randint(
                10 ** (LEN_VOTER_ID - 1), (10**LEN_VOTER_ID) - 1
            )
            while n in used_ids:
                n = random.randint(
                    10 ** (LEN_VOTER_ID - 1), (10**LEN_VOTER_ID) - 1
                )
            voter_ids.append(str(n))
            used_ids.add(n)

        self.df.insert(
            loc=len(self.df.columns), column="voter_id", value=voter_ids
        )

        survey_ids = []
        used_ids = set()
        for _ in range(len(self.df)):
            random.seed(time.time())
            n = random.randint(
                10 ** (LEN_SURVEY_ID - 1), (10**LEN_SURVEY_ID) - 1
            )
            while n in used_ids:
                n = random.randint(
                    10 ** (LEN_SURVEY_ID - 1), (10**LEN_SURVEY_ID) - 1
                )
            survey_ids.append(str(n))
            used_ids.add(n)

        self.df.insert(
            loc=len(self.df.columns), column="survey_id", value=survey_ids
        )

    def set_config(self, file):
        """
        Fetch configuration settings from .toml file
        """
        try:
            self.log("Fetching configuration...")
            self.config = toml.load(file)
            self.check_config()
        except Exception as e:
            self.log("{}: {}".format(e.__class__.__name__, str(e)))
            self.exit(-1)

    def check_config(self):
        """
        Basic validation for configurations settings for the election. Exits
        if any of the checks are not met.
        """
        try:
            if not all(
                key in self.config
                for key in [
                    "vote_type",
                    "form_url",
                    "worksheet_url",
                    "worksheet_title",
                    "vote_title",
                    "voters_file",
                    "voters_sheet",
                    "quorum",
                ]
            ):
                self.log("FATAL: Configuration file missing fields")
                self.exit(-1)
            if self.config["vote_type"] not in self.VOTE_TYPES:
                self.log("FATAL: Invalid vote type")
                self.exit(-1)
            if not self.config["form_url"].startswith(
                "https://docs.google.com/forms/"
            ):
                self.log("FATAL: Invalid form URL")
                self.exit(-1)
            if not os.path.exists("fetch_token/token.json"):
                self.log(
                    "FATAL: Please run the Go script to generate authorized user token before running the elections script"
                )
                self.exit(-1)

        except Exception as e:
            self.log(e)
            self.exit(-1)

    def confirm_config(self):
        """
        Prints the configuration of the vote and asks for manual confirmation
        from the person running the script.
        """
        self.log("Confirming vote configuration...")
        o = "\n" + "\n".join(
            ["{}: {}".format(key, self.config[key]) for key in self.config]
        )
        print(o)

        confirm = input("Does this configuration look correct? [y/n]: ")
        if confirm == "y" or confirm == "Y":
            self.log("Vote configuration confirmed by election official")
        else:
            self.log("Vote configuration denied by election official")
            self.exit(-1)

    def repair_token(self):
        """
        Fills in necessary client_id and client_secret for the access token file,
        since for some reason Google doesn't generate them.
        """
        self.log("Repairing access token...")

        with open("fetch_token/token.json", "r") as old:
            token = json.load(old)

        with open("oauth.json") as oauth:
            oauth = json.load(oauth)

        if "client_id" not in token:
            token["client_id"] = oauth["installed"]["client_id"]
        if "client_secret" not in token:
            token["client_secret"] = oauth["installed"]["client_secret"]

        with open("authorized_user.json", "w") as new:
            json.dump(token, new)

        self.log("Access token repaired!")

    def refresh_credentials(self, log=True):
        """
        Uses the refresh token to refresh authorized credentials for the Oauth
        user. If you want to change which user is being logged in, delete
        the file and rerun the authorization fetcher script.
        """
        if not self.creds.valid:
            if log:
                self.log("Refreshing credentials...")

            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())

            with open("authorized_user.json", "w") as token:
                token.write(self.creds.to_json())

            self.service = build("gmail", "v1", credentials=self.creds)

            self.gc = gspread.oauth(
                credentials_filename="oauth.json",
                authorized_user_filename="authorized_user.json",
            )

            self.sh = self.gc.open_by_url(self.config["worksheet_url"])
            self.worksheet = self.sh.worksheet(self.config["worksheet_title"])

            if log:
                self.log("Credentials refreshed!")

    def set_worksheet(self):
        """
        Retrieves the worksheet from Google Sheets using the configuration
        file urls
        """
        try:
            self.log("Fetching results spreadsheet...")
            self.refresh_credentials(log=False)
            self.gc = gspread.oauth(
                credentials_filename="oauth.json",
                authorized_user_filename="authorized_user.json",
            )
            self.sh = self.gc.open_by_url(self.config["worksheet_url"])
            self.worksheet = self.sh.worksheet(self.config["worksheet_title"])
        except Exception as e:
            self.log("{}: {}".format(e.__class__.__name__, str(e)))
            self.exit(-1)

    def update_votes(self):
        """
        Fetches votes from the Google Form response Sheet. Exits if any tampering
        is detected.
        """
        self.refresh_credentials(log=False)

        raw = self.retry(self.worksheet.get_values)
        if self.votes is not None:
            new = pd.DataFrame(data=raw[1:], columns=raw[0])
            if not self.votes.equals(new.head(n=len(self.votes))):
                self.log("FATAL: Tampering detected, previous votes modified.")
                self.exit(-2)
            else:
                self.votes = new
        else:
            self.votes = pd.DataFrame(data=raw[1:], columns=raw[0])

    def verify_email(self):
        try:
            self.log("Verifying email...")

            self.creds = Credentials.from_authorized_user_file(
                "authorized_user.json", SCOPES
            )

            self.service = build("gmail", "v1", credentials=self.creds)

            self.log("Email verified!")
        except Exception as e:
            self.log("{}: {}".format(e.__class__.__name__, str(e)))
            self.log(e)
            self.exit(-1)

    def email_links(self):
        self.log("Sending election links...")
        self.refresh_credentials()

        sent_message_ids = []
        for _, row in self.df.iterrows():
            with open("email_links.txt", "r") as f:
                content = f.read()

            fields = {}

            if pd.isnull(row["nickname"]):
                fields["name"] = row["first_name"]
            else:
                fields["name"] = row["nickname"]

            fields["link"] = self.config["form_url"] + row["voter_id"]
            fields["voter_id"] = row["voter_id"]
            fields["survey_id"] = row["survey_id"]

            message = EmailMessage()
            message.set_content(content.format(**fields))
            message["To"] = row["email"]
            message["From"] = "averyexcomm@gmail.com"
            message["Subject"] = self.config["vote_title"]

            encoded_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode()

            send_message = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": encoded_message})
                .execute
            )

            sent_message = self.retry(send_message)

            sent_message_ids.append(sent_message["id"])

        self.log("Emails sent!")

        self.log("Deleting emails...")

        delete_messages = (
            self.service.users()
            .messages()
            .batchDelete(userId="me", body={"ids": sent_message_ids})
            .execute
        )

        self.retry(delete_messages)

        self.log("Emails deleted!")

    def email_tampering(self):
        # TODO: email out notification of tampering
        # for now the code will fail and be sent for a manual recount,
        # since any errors are most likely due to bugs
        pass

    def email_results(self, results):
        self.log("Sending election results...")
        self.refresh_credentials()

        with open("email_results.txt", "r") as f:
            content = f.read()

        sent_message_ids = []
        for _, row in self.df.iterrows():
            fields = {}

            if pd.isnull(row["nickname"]):
                fields["name"] = row["first_name"]
            else:
                fields["name"] = row["nickname"]

            fields["results"] = results

            fields["survey_id"] = row["survey_id"]

            message = EmailMessage()
            message.set_content(content.format(**fields))

            message.add_attachment(
                "\n".join(self.logs).encode("utf-8"),
                maintype="text",
                subtype="plain",
                filename="logs.txt",
            )

            message["To"] = row["email"]
            message["From"] = "averyexcomm@gmail.com"
            message["Subject"] = "RESULTS: " + self.config["vote_title"]

            encoded_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode()

            send_message = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": encoded_message})
                .execute
            )

            sent_message = self.retry(send_message)

            sent_message_ids.append(sent_message["id"])

        self.log("Emails sent!")

        self.log("Deleting emails...")

        delete_messages = (
            self.service.users()
            .messages()
            .batchDelete(userId="me", body={"ids": sent_message_ids})
            .execute
        )

        self.retry(delete_messages)

        self.log("Emails deleted!")

    def get_valid_votes(self):
        valid = self.votes.loc[
            self.votes[self.votes.columns[-1]].isin(self.df["voter_id"])
        ]

        valid = valid.drop_duplicates(subset=valid.columns[-1], keep="last")

        return valid

    def get_results_selective(self):
        self.log("Started computing results for election...")

        self.update_votes()

        positions = []
        candidates = {}
        valid_votes = self.get_valid_votes()

        results = []

        p = parse.compile("{} [{}]")

        for i in range(1, len(valid_votes.columns) - 1):
            pos, cand = p.parse(valid_votes.columns[i])
            if pos not in positions:
                positions.append(pos)
                candidates[pos] = []
            candidates[pos].append(cand)

        for pos in positions:
            self.log("-" * 80)
            self.log("Starting runoff for {}".format(pos))

            pos_votes = valid_votes[
                [col for col in valid_votes if parse.parse(pos + " [{}]", col)]
            ].astype(int)

            pos_votes.columns = [p.parse(col)[1] for col in pos_votes.columns]

            if "Abstain" in pos_votes.columns:
                pos_votes = pos_votes[pos_votes["Abstain"] != 1]
                pos_votes = pos_votes.drop("Abstain", axis=1)

            r = 1
            winner = None
            while winner is None:
                self.log("Round {}:".format(r))

                num_votes = (pos_votes == 1).sum()

                for cand in pos_votes.columns:
                    self.log("    {}: {}".format(cand, num_votes[cand]))

                    if num_votes[cand] > len(pos_votes) / 2:
                        winner = cand

                if winner is None:
                    elim = [
                        cand
                        for cand in pos_votes.columns
                        if num_votes[cand] == num_votes.min()
                    ]

                    e = random.choice(elim)

                    self.log("Candidate {} eliminated".format(", ".join(e)))
                    pos_votes = pos_votes.drop(e, axis=1)

                    pos_votes = pos_votes.subtract(
                        pos_votes.min(axis=1), axis=0
                    ).add(1)
                r += 1

            self.log("Winner: {}".format(winner))
            results.append("{}: {}".format(pos, winner))

            self.log("-" * 80)

        return "\n".join(results)

    def get_results_referendum(self, prop):
        self.log("Started computing results for election...")

        self.update_votes()

        valid_votes = self.get_valid_votes()

        results = []

        for a in valid_votes.columns:
            self.log("-" * 80)

            res = valid_votes[a].value_counts()

            y = res["YES"]
            n = res["NO"]

            results.append(a)
            self.log(a)

            if y / (y + n) >= prop:
                results.append("PASSED ({} YES, {} NO)".format(y, n))
                self.log("PASSED ({} YES, {} NO)".format(y, n))
            else:
                results.append("REJECTED ({} YES, {} NO)".format(y, n))
                self.log("REJECTED ({} YES, {} NO)".format(y, n))

            self.log("-" * 80)

        return "\n".join(results)

    def retry(self, func, max_attempts=10000, timeout=2):
        try:
            ret = func()
            return ret
        except:
            self.log(
                "Starting automatic retries for function {}".format(
                    func.__name__
                )
            )
            attempts = 0
            while attempts < max_attempts:
                try:
                    attempts += 1
                    ret = func()
                    break
                except:
                    self.check_internet(log=False)
                    time.sleep(timeout ** (attempts // 10))
            if attempts == max_attempts:
                self.log("Automatic retries failed, unable to connect.")
                self.exit(-1)
            else:
                self.log("Action successful after {} attempts".format(attempts))
                return ret

    def run_election(self):
        self.log("Election started!")
        self.check_internet(log=True)

        self.repair_token()

        self.confirm_config()

        self.set_voters(self.config["voters_file"])

        self.confirm_voters()

        self.set_worksheet()
        self.verify_email()

        self.generate_voter_ids()

        self.email_links()
        self.update_votes()

        while len(self.get_valid_votes()) < self.config["quorum"]:
            self.log("Starting 24 hour voting period...")
            start = time.time()
            while time.time() - start < QUORUM_TIME_LIMIT:
                self.update_votes()
                time.sleep(5)
            self.update_votes()
            self.log(
                "{} valid votes collected out of {} for quorum".format(
                    len(self.get_valid_votes()), self.config["quorum"]
                )
            )

        self.log("Quorum Reached!")

        if self.config["vote_type"] == "selective":
            results = self.get_results_selective()
        elif self.config["vote_type"] == "referendum":
            results = self.get_results_referendum(1 / 2)
        elif self.config["vote_type"] == "2/3 referendum":
            results = self.get_results_referendum(2 / 3)

        self.email_results(results)

        self.exit(0)


if __name__ == "__main__":
    ov = OnlineVote()
    ov.run_election()

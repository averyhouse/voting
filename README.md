# Caltech Avery House Online Voting Project

---

# Goals:

1. Create a free, secure, transparent, anonymized, convinient online voting
   system.
2. Remove the need for "middleman" survey services.
3. Avery House glory.

# Summary:

This framework interfaces Google surveys with Python for a clean front end and
back end. The voting system allows simple referendum voting as well as the more
complex IRV (instnt runoff voting) strategy. The workflow can be summarized as:

1. Manually create a Google survey and link it to a Google spreadsheet. Enter
   the link to the survey into the Python script.

2. Python script generates unique links to the survey and emails out links. One
   link per email addresses. These links can be hardcoded or read from a Google
   doc (default)

3. Results automatically go into the linked Google Spreadsheet. As the script
   waits for the time limit to be reached, it actively checks the spreadsheet
   for tampering.

4. When the voting period has ended, the Python script reads in the results from
   this spreadsheet, parses it, and calculates the winners based on instant
   runoff. The results are automatically emailed out.

# Security and anonymity:

1. The python script generates a unique 128-digit-time-seeded random int for
   each email address that is eligible to vote. This number is embedded in the
   URL of the Google survey link and is automatically added to the “voter ID”
   field in the survey. When votes are read from the Python script, it will
   check the “voter ID” field of submitted votes and confirms that they
   corresponding to originally-generated ID.This makes it so
   duplicate/unauthorized votes can be invalidated.

2. Every email also contains a randomly-generated 4 digit pin which represents
   the survey ID. This survey ID is sent in the initial email as well as the
   results email. Every voter should see the same survey ID but different voters
   see differnt survey IDs. The purpose of the survey ID is prevent a scenario
   where someone termiantes the script and sends out fake results emails.

3. The voter/survey IDs are not stored anywhere except in the python script’s
   internal state. This is possible because the script does not finish executing
   until the final email results are sent out. This prevents manipulation of
   IDs, ensures that vote results can not be modified, and maintains
   confidentiality of voters. Furthermore, the “sent” folder of the gmail
   account hosting the survey has its sent box deleted after the emails get
   sent - this prevents people with access to the email account from seeing
   which IDs were associated with specific email addresses.

4. If someone manually adds a vote to the spreadsheet, it will certainly not
   have a valid 128-digit entry and will be invalidated in the final count.

5. While the script waits for quorum to be reached, it periodically compares a
   local copy of all voter data with the most recent batch of voter data. If the
   recent data is missing any of the old data, the script emails all voters that
   the spreadsheet has been tamepred with and terminates. If, by luck, the
   manipulation occurs before a refresh of the local data, a second layer of
   security is used - the election results will contain a list of all data from
   the vote, including the IDs associated with each vote. If someone believes
   their vote has been deleted, they can compare their voter ID (in the email)
   with the voter IDs found in the raw vote data which is automatically emailed
   at the end of a vote.A thrid layer of security is in the Google spreadsheet
   hosting the survey results which will contain all edit history of the
   spreadsheet. The edit history can be referenced if a votes legitimacy falls
   into question

6. Adding non-eligible emails to the eligible voter list is easily spotted since
   the email with the results also contains a list of all emails (xlsx format)
   that participated in the survey. All eligible voters are emailed the raw vote
   data (xlsx format) in the results email.

---

# Requirements

- Python 3.x installation
- Git installation
- packages in `requirements.txt`
- Oauth key for a Google Cloud Project with Sheets, Drive, and Gmail APIs
  enabled

# Instructions for server

1. Fill in the `config.toml` file as described in
   [Filling out the config file](#filling-out-the-config-file) on your local
   computer.
2. Copy the config file to the server using
   `scp /local/path/config.toml voting@avery.caltech.edu:~/voting`
   > You will be prompted for a password. It will be in the Excomm drive with
   > the Avery account passwords.
3. Download an OAuth key from Google Cloud by:
   1. Navigate to `console.cloud.google.com`
   2. Select the project `OnlineVoting` in the project menu (top left)
   3. Use the menu (top left) to navigate to `APIs & Services > Credentials`
   4. Download the `OnlineVoting` OAuth 2.0 Client ID as `oauth.json`
4. Copy the `oauth.json` file to the server using
   `scp /local/path/oauth.json voting@avery.caltech.edu:~/voting`
   > This file may already be in the server folder, be sure to check before
   > doing steps 3 and 4.
5. SSH into the server using `ssh voting@avery.caltech.edu`
6. Navigate into the directory using `cd voting`
7. (Optional) Update the server code by running `git pull origin master`
8. Attempt to open tmux by typing `tmux attach`. If this says "no sessions, then
   start tmux by running `tmux`.
9. Activate the virtual environment by running `source ./venv/bin/activate`
10. Run the script using `python election.py`
11. Press `Ctrl+B, D` to detach from tmux. The script will now be running with
    very little risk of interrupts. If you want to check on progress, run
    `tmux attach` and detach with `Ctrl+B, D` when you're done.

# Filling out the config file

- `vote_type`: link to Google form
  - needs to end in `viewform?usp=pp_url&entry.#########=`
- `responses_url`: link to Google sheet where the form responses go
  - click "Share -> Get link"
  - make sure the sheet is shared with `averyexcomm@gmail.com`
- `responses_sheet`: name of the sheet in Google sheets
  - name on the bottom tab
- `vote_title`: title of the election
  - this will show up in the subject line when the emails are sent out
- `voters_file`: Google sheet or csv file with names and emails of all voters
  - this sheet must have columns titled "First Name", "Nickname", "Last Name",
    and "Email"
- `quorum`: number of votes necessary to conclude the voting period

# Instructions for a local machine (DEPRECATED, WORK IN PROGRESS)

1. Install Python (test using `python --version`)
2. Install Git (test using `git version`)
3. `git clone` this repository to create a local copy.
4. Download an OAuth key from Google Cloud by:
   1. Navigate to `console.cloud.google.com`
   2. Select the project `OnlineVoting` in the project menu (top left)
   3. Use the menu (top left) to navigate to `APIs & Services > Credentials`
   4. Download the `OnlineVoting` OAuth 2.0 Client ID as `oauth.json` and save
      this in the `voting` directory
5. Run the script to validate credentials by opening a command shell, running
   `cd fetch_token` to move into the `fetch_token` directory, and running
   `go run fetch_token.go`.
   1. In the command line, this will print out a URL with a prompt to authorize
      by following the link. Copy paste this link into a browser window. 2.
      Select the averyexcomm@gmail.com account to log into. After logging in,
      you will get a warning about an unverified app (Don't worry, this app is
      safe :D). Hit `Advanced > Go to ov (unsafe)` to ignore the warning. 3.
      Check all the boxes to give all permissions to the script. 4. You will now
      get an error that says `localhost refused to connect`. Go to the URL in
      the address bar. You should see something like
      `...&code=<long-string>&scope=...` in the URL. 5. Copy the string after
      `&code=` and paste it into the command line after the authentication URL
      and hit Enter. 6. This should create a file called `token.json` in the
      `fetch_token` directory. If this worked correctly, it should also print
      out all the email labels/folders found on the account in the command line.
6. Install the requirements to run the python script by running
   `pip install -r requirements.txt`
7. Configure the settings in `config.toml` with:
   - vote type: must be either "selective", "referendum", or "2/3 referendum".
     If the vote type is "selective", the choices must be multiple choice grid
     rankings. If the vote type is a referendum type, the questions must be
     multiple choice with options "YES", "NO", or "Abstain".
   - form URL: must be prefilled link to Google Forms. See below on how to get
     link.
   - worksheet URL: sheet with results from form, shared with
     averyexcomm@gmail.com
   - sheet title: i.e. "Form Responses 1" from above
   - vote title: i.e. xxxx Avery Excomm Election
   - voters list: can either be a Google Sheet URL or a CSV text file
   - voters sheet title: if using a Google Sheet, i.e. "Sheet1"
   - quorum
8. Check that each Google Sheet has been shared with averyexcomm@gmail.com.
9. You are now ready to run the script! Run `python election.py` to start the
   script! DO NOT TOUCH IT ONCE THE SCRIPT HAS STARTED!! Everything will happen
   automatically, be sure that your computer stays on and the window with the
   command line stays open.

# Forms and Sheets

1. A manually-created Google Survey (if you want to do an IRV vote)

   - The survey questions must be multiple choice grids
   - For every candidate, make a new column with a "rank"
   - Ranks go from 1 to num_candidates with 1 being the best
   - Last question must be a short answer question that holds voter ID
   - Get the URL from the pre-fill link such that values appended to the URL
     automatically fill in "voter ID"
   - This URL looks something like:
     https://docs.google.com/forms/d/xxx...xxx/viewform?entry.1299711861=
   - Required survey option: 1 response per column
   - Suggested survey options: shuffle row order, disable all confirmation page
     links
   - Example of a valid IRV Google survey:
     ![alt tag](imgs/example%20correct%20survey%20format.png)

2. A manually-created Google Survey (If you want to do a simple referendum vote)

   - The survey questions must be multiple choice
   - Last question must be a short answer question that holds voter ID
   - Get the URL from the pre-fill link such that values appended to the URL
     automatically fill in "voter ID"
   - This URL looks something like:
     https://docs.google.com/forms/d/xxx...xxx/viewform?entry.1299711861=
   - Suggested survey options: shuffle question order, disable all confirmation
     page links

3. A new, blank worksheet in your linked spreadsheet (step 3) with a unique
   name.
   - This worksheet must be created manually and specified as the data
     destination when creating the survey (step 4)
   - Trying to re-use worksheets will result in failure
   - This step must be completed for every new survey
     ![alt tag](imgs/worksheet%20guide.png)

# Notes:

When choosing a local machine to run this script on, keep in mind that the
script's execution can not be interrupted or the vote will end. Additionally,
the script needs to internet access throughout the duration of its execution
time so that it can actively check for vote manipulation. If you are using Linux
to run the script, I highly reccomend runing the script inside a tmux session to
avoid accidentally canceling the script.

It is highly reccomended that the script be downloaded directly from this repo
and executed in plain sight of several representatives to prevent illicit script
modification.

The last few numeric global variables may be tweaked to fit your survey's
specific needs.

The script should should be portable and has been tested on Windows 10 and
Ubuntu 14

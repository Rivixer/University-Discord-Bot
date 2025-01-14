# SGGW-inf-bot-discord

This is a Discord Bot created to manage server for computer science students of the Faculty of Applied Informatics
and Mathematics at the Warsaw University of Life Sciences (2021/2025).

Python version: 3.12

## How to configure the bot?

**CREATE THE DISCORD SERVER**

1. On the left side of the Discord, click `+` to add a server
2. Select `Create your own` and skip the next question
3. You can name the server or add an icon
4. Click on `create`
5. Enable `developer mode` in Discord (go to user settings and select `advanced` category)

**CREATE AND ADD A BOT TO SERVER**

1. Go to https://discord.com/developers/applications and click on `New Application`
2. Enter the name you want
3. Choose `Bot` on the left side
4. Click on `Add Bot` and then `Yes, do it` on the next page
5. Then turn on `Presence intent`, `Server members intent` and `Message content intents`
6. Next to the bot icon, click `reset token` and copy the bot token for later
7. On the left side, choose `OAuth2` and `URL Generator`
8. In `skopes` select `bot`, in `bot permissions` choose `Adminstrator`
9. Copy and paste the link below into the search bar
10. Choose your server
11. Click on `continue` and `authorize` without unchecking the `Administrator` box
12. Pass the hCaptcha

**START THE BOT**

0. Make sure you have the correct version of python installed :)
1. Clone the repository
2. Create a `.env` file in the root directory of the repository 
3. Add this line to `.env`:
   ```
   BOT_TOKEN= /bot token copied in step 6 of previous topic/
   ```
4. Initialize the virtual environment:
    1. Open the console in the bot folder
    2. Install virtualenv, if you don't have it - type `pip install virtualenv` in the console
    3. Enter `virtualenv .venv` in the console
    4. Enter `source .venv/bin/activate` in the console to activate virtualenv
5. Install the requirement packages:
    1. Make sure the virtual environment is selected
    2. Type `pip install -r requirements.txt` in the console
6. Enter `py main.py` in the console to run the bot.

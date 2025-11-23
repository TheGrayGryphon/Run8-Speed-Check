# Run8-Speed-Check
A bot for keeping track of players' train speeds during normal operations. It can report locally to just the console, or optionally also to Discord as a bot user. This works by interfacing with DispatcherComms.dll in your main install directory of Run8. **A special thanks to [@Garrisonsan](https://github.com/Garrisonsan) and [@sjstein](https://github.com/sjstein) (aka Sinistar) for helping overcome my user-issues.**

This is created using Python 3.12.10, it will NOT work with any later version of Python due to *pythonnet* library dependencies. For instructions on how to make your Discord bot, youtube is your friend. If you ask me how to set it up, I will just repeat the instructions in a youtube video.

Setup Instructions:
* Create your python virtual environment, ensure you use a python 3.12 version. 
  * If you have multiple python versions installed, use `py -3.12 -m venv R8S`
  * `.\R8S\Scripts\activate`
  * `pip install -r requirements.txt`
* Adjust the DispatcherCommsPath in SpeederSettings.json. This file is where you input all of your settings. It's just a text file with an abnormal extension, so it can be opened with nearly any text file editor.
> [!NOTE]
> Formatting matters, so edit carefully!  Anywhere in your path that there is a backslash, you need to "escape" it by typing two of them, as in the example included in the json file already (`F:\\Games\\Run8\\DispatcherComms.dll`).  Pay attention not to add or remove any punctuation characters you didn't intend to, including quotation marks.  Every line item except the last one must end in a comma.

* Add any Discord information such as the: 
  * DiscordBotToken: required if you want anything on Discord to work.  This assumes you have already created, setup, and joined the bot to your Discord server through the Discord Developer portal.
  * DiscordEnabled: set to true if you want to use Discord or you'll just have a fancy terminal program that shows you what's happening
  * DiscordAlertChannel: ID number, not the name - right click the channel name on Discord and copy the ID. Ideally a channel monitored by staff only, but this is up to you :)
  * DiscordStatusChannel: ID number - a channel that doesn't need active monitoring.  This lets staff read through the history and determine if a user has a habit of speeding/hard couples.
  * DiscordAlertRole: ID - not the name but the ID number. If you want to have the bot add a ping to that role ID for excessive speed messages. Leave 0 to disable.  You can manually edit any of the messages in the json to add this functionality to other messages.
* Edit any necessary parameters related to your desired behavior for the bot:
  * AlertSpeed: When player train speed is AlertSpeed MPH > TrainSpeedLimitMPH, tracking starts.
  * AlertSpeedTimer: If the player remains AlertSpeed > TrainSpeedLimitMPH for AlertSpeedTimer seconds, send a message to the console and Discord (if configured).
  * OverSpeed: When player train speed is OverSpeed MPH > TrainSpeedLimitMPH, an excessive speed message is sent to the console and Discord (if configured as above).
  * HardCoupleSpeed: If the AxleCount of a player's train increases and their last known speed was > HardCoupleSpeed MPH, send a message to the console and Discord (if configured).
  * DispatcherCommsPath: Point this to your main Run8 directory, where your DispatcherComms.dll is already installed.
  * PeriodAnnounceTimer: If not 0, send AutomatedNoticeMsg and PeriodicAnnounceMsg every seconds to Run8 so they appear in game on Channel 00.
  * VerboseLogging: If true, all routine (non-alert) messages will be sent to Discord.  If false, only alert messages will be sent to Discord (but everything is still printed to the console).
* Edit the following special case settings if needed:
  * SuperCAlertSpeed: The speedy intermodals that were capable of passenger speeds will have their TrainSpeedLimitMPH offset by the numeric value.
  * SuperCTrainSymbols: Comma delimited list of train symbols for the special speed limit. Do not include spaces, and partial symbols are ok.
  * TronaAlertSpeed: Many players allow for 40mph operation, so the TrainSpeedLimitMPH needs to be offset in all blocks in the Trona DLC that have 25mph speed limits.
  * TronaRouteID: Defines the route ID the program looks for to determine which block sections to apply the TronaAlertSpeed to. Normally this will not be changed.

Launch Instructions: 
Create a batch file using the examplebat.txt after creating your python virtual environment.
Once the batch file launches, the bot will:
* Look for an instance of Run8
* Remind you to enable `External DS`
> [!TIP]
> We recommend that you configure your Run-8 instance to start in server mode using the ServerConfig.xml option provided by Run-8.  Automatically enabling External DS is a configurable option.  With some knowledge of how to write batch files, a single batch file can launch both Run-8 and (after a delay) your Speeder bot.

* Connect to Discord if configured to do so in the SpeederSettings.json file
* Send a startup complete message


# Run8-Speed-Check
A bot for keeping track of players speed during normal operations. It can report locally to just the console, or to Discord Channels. This works by interfacing with DispatcherComms.dll in your main install directory of Run8. A special thanks to Garrison and Sinistar for helping overcome my user-issues.

This is created using Python 3.12.10, it will NOT work with any later version of Python due to *pythonnet* library dependencies. For instructions on how to make your Discord bot, youtube is your friend. If you ask me how to set it up, I will just repeat the instructions in a youtube video.

Setup Instructions:
* Create your python virtual environment, ensure you use a python 3.12 version. 
  * If you have multiple python versions installed, use `py -3.12 -m venv R8S`
  * `.\R8S\Scripts\activate`
  * `pip install -r requirements.txt`
* Adjust the DispatcherCommsPath in the json file. The .json file is where you input all of your settings. It's just a text file with an abnormal extension, it can be opened with nearly any text file editor.
* Add any Discord information such as the: 
  * Bot token
  * Enabled to true
  * Alert channel ID not the name, but the Channel ID number (a channel that is actively monitord by staff)
  * Status channel ID (a channel that doesn't need active monitoring, this lets staff read through the history and determine if a user has a habit of speeding/hard couples)
  * Discord Alert Role ID, if you want to edit the Messages to ping/notify your staff when they are triggered. I leave mine blank.
* Alert Speed: When player train speed is > TrainSpeedLimitMPH, tracking starts.
* Alert Speed Timer: If the player remains Alert Speed > TrainSpeedLimitMPH for a certain amount of time, send a message. (configure the message on Line 425, program.cs)
* Over Speed: When player train speed is > TrainSpeedLimitMPH, a separate message is sent. (configure the message on Line 415, program.cs)
* Hard Couple Speed: If the AxleCount of a players train increases, use the previously reported speed in mph. (configure the message on Line 322, program.cs)
* DispatcherCommsPath: Point this to your main Run8 directory, where your DispatcherComms.dll is already installed.
Special Cases:
* Super C: The speedy intermodals that were capable of passenger speeds will have their TrainSpeedLimitMPH offset by the numeric value. The entered symbols are comma delimted, no spaces, and only need to contain part of the symbol
* Trona: Many players allow for 40mph operation, so the TrainSpeedLimitMPH needs to be offset in all blocks in the Trona DLC that have 25mph speed limits. 

Launch Instructions: 
Create a batch file using the examplebat.txt after creating your python virtual environment.
Once the batch file launches, the bot will:
* Look for an instance of Run8
* Remind you to enable `External DS`
* Connect to Discord if configured to do so in the json file
* Send a startup complete message


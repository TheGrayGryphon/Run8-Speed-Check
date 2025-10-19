# Run8-Speed-Check
A bot for keeping track of players speed during normal operations. It can report locally to jsut the console, or to Discord Channels. This works by interfacing with DispatcherComms.dll in your main install directory of Run8. 


The .props file is where you input all of your settings. It's just a text file with an abnormal extension. 

* Alert Speed: When player train speed is > TrainSpeedLimitMPH, tracking starts.
* Alert Speed Timer: If the player remains Alert Speed > TrainSpeedLimitMPH for a certain amount of time, send a message. (configure the message on Line 425, program.cs)
* Over Speed: When player train speed is > TrainSpeedLimitMPH, a separate message is sent. (configure the message on Line 415, program.cs)
* Hard Couple Speed: If the AxleCount of a players train increases, use the previously reported speed in mph. (configure the message on Line 322, program.cs)

Special Cases:
* Super C: The speedy intermodals that were capable of passenger speeds will have their TrainSpeedLimitMPH offset by the numeric value. The entered symbols are comma delimted, no spaces, and only need to contain part of the symbol
* Trona: Many players allow for 40mph operation, so the TrainSpeedLimitMPH needs to be offset in all blocks in the Trona DLC that have 25mph speed limits. 

Discord settings:
* Discord Enabled: Falso if there's no integration with discord, true if you want reporting sent to channels
* Discord Bot Token: When setting up your Discord Bot in the Developer Portal, get the code and paste it here
* Discord Alert Channel: This is wwhere egregious warnings are sent and will indicate server stability is at risk, a staff only channel is wise
* Discord Status Channel: The bot will send player status messages as they happen, useful for tracking down a players habbits. 

For instructions on how to make your Discord bot, youtube is your friend. If you ask me how to set it up, I will just repeat the instructions in a youtube video.


using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.IO;
using System.Reflection;
using DispatcherComms;
using DispatcherComms.Run8Proxy;
using DispatcherComms.MessagesFromRun8;
using Discord;
using Discord.WebSocket;

namespace Speeder
{
    class Program
    {
        private static IRun8 mRun8;
        private static readonly object lockObj = new object();
        private static readonly Dictionary<int, DateTime> activePlayers = new Dictionary<int, DateTime>();
        private static readonly Dictionary<int, DateTime> speedingStart = new Dictionary<int, DateTime>();
        private static readonly Dictionary<int, double> maxOverspeed = new Dictionary<int, double>();
        private static readonly HashSet<int> overSpeedWarned = new HashSet<int>();
        private static readonly HashSet<int> sustainedWarned = new HashSet<int>();
        private static readonly Dictionary<int, int> lastAxleCount = new Dictionary<int, int>();
        private static readonly Dictionary<int, double> lastSpeed = new Dictionary<int, double>();
        private static readonly Dictionary<int, EEngineerType> lastEngineerType = new Dictionary<int, EEngineerType>();
        private static readonly Dictionary<int, string> lastPlayerName = new Dictionary<int, string>();
        private static readonly Dictionary<int, string> lastTrainSymbol = new Dictionary<int, string>();

        private static DateTime lastSimTime = DateTime.MinValue;
        private static bool hasWarnedNoRun8 = false;
        private static bool isConnected = false;
        private static bool hasReceivedData = false;
        private static bool startupComplete = false;

        // Settings
        private static double alertSpeed = 5;
        private static double overSpeed = 20;
        private static int alertSpeedTimer = 300;
        private static double hardCoupleSpeed = 7;
        private static double tronaAlertSpeed = 20;
        private static int tronaRouteID = 320;
        private static double superCAlertSpeed = 25;
        private static string superCTrainSymbols = "991,981,119,198,Super";

        // Discord
        private static bool discordEnabled = false;
        private static string discordToken = "";
        private static ulong discordAlertChannel = 0;
        private static ulong discordStatusChannel = 0;
        private static DiscordSocketClient discordClient;

        static void Main(string[] args)
        {
            System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12;
            Console.Title = "Speeder - Player Train Tracker (.NET 4.5)";
            Console.WriteLine("=== Speeder: Player Train Tracker ===");
            Console.WriteLine("Attempting to connect to Run8 External Dispatcher Interface...");
            Console.WriteLine("Press ENTER to exit program at any time.");

            LoadSettings();

            if (discordEnabled)
                Task.Run(async () => await StartDiscordBot());

            try
            {
                mRun8 = Run8ProxyFactory.GetRun8Proxy();
                mRun8.Connected += OnConnected;
                mRun8.Disconnected += OnDisconnected;
                mRun8.TrainData += OnTrainData;
                mRun8.SimulationState += OnSimulationState;
                mRun8.Start("localhost", DispatcherProxyFactory.DefaultExternalDispatcherPort);

                bool connected = false;
                for (int i = 0; i < 50; i++)
                {
                    Thread.Sleep(100);
                    lock (lockObj)
                    {
                        if (isConnected) { connected = true; break; }
                    }
                }

                if (!connected && !hasWarnedNoRun8)
                {
                    Console.WriteLine("[WARN] Unable to connect to Run8 - no instance found within 5 seconds.");
                    Console.WriteLine("Please launch Run8 and enable 'Allow External DS' in the Sim-Options Menu.\n");
                    hasWarnedNoRun8 = true;
                }

                Thread monitorThread = new Thread(MonitorPlayerTrains)
                {
                    IsBackground = true
                };
                monitorThread.Start();

                Console.ReadLine();
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error: " + ex.Message);
            }
        }

        private static void LoadSettings()
        {
            try
            {
                string propsFile = "SpeederSettings.props";
                if (!File.Exists(propsFile))
                {
                    Console.WriteLine("SpeederSettings.props not found. Using defaults.\n");
                    return;
                }

                foreach (string raw in File.ReadAllLines(propsFile))
                {
                    string line = raw.Trim();
                    if (!line.StartsWith("<") || !line.Contains(">")) continue;

                    if (line.Contains("<AlertSpeed>")) alertSpeed = double.Parse(Extract(line));
                    else if (line.Contains("<OverSpeed>")) overSpeed = double.Parse(Extract(line));
                    else if (line.Contains("<AlertSpeedTimer>")) alertSpeedTimer = int.Parse(Extract(line));
                    else if (line.Contains("<HardCoupleSpeed>")) hardCoupleSpeed = double.Parse(Extract(line));
                    else if (line.Contains("<TronaAlertSpeed>")) tronaAlertSpeed = double.Parse(Extract(line));
                    else if (line.Contains("<TronaRouteID>")) tronaRouteID = int.Parse(Extract(line));
                    else if (line.Contains("<SuperCAlertSpeed>")) superCAlertSpeed = double.Parse(Extract(line));
                    else if (line.Contains("<SuperCTrainSymbols>")) superCTrainSymbols = Extract(line);
                    else if (line.Contains("<DiscordEnabled>")) discordEnabled = Extract(line).ToLower() == "true";
                    else if (line.Contains("<DiscordBotToken>")) discordToken = Extract(line);
                    else if (line.Contains("<DiscordAlertChannel>")) ulong.TryParse(Extract(line), out discordAlertChannel);
                    else if (line.Contains("<DiscordStatusChannel>")) ulong.TryParse(Extract(line), out discordStatusChannel);
                }

                Console.WriteLine("Loaded settings: alert=" + alertSpeed +
                    ", overspeed=" + overSpeed +
                    ", timer=" + alertSpeedTimer + "s, HardCoupleSpeed=" + hardCoupleSpeed +
                    ", Trona=" + tronaAlertSpeed + ", SuperC=" + superCAlertSpeed + "\n");
            }
            catch (Exception ex)
            {
                Console.WriteLine("Failed to load SpeederSettings.props: " + ex.Message);
            }
        }

        private static string Extract(string line)
        {
            int s = line.IndexOf('>') + 1;
            int e = line.LastIndexOf('<');
            return (s > 0 && e > s) ? line.Substring(s, e - s).Trim() : "";
        }

        private static async Task StartDiscordBot()
        {
            try
            {
                DiscordSocketConfig cfg = new DiscordSocketConfig();
                cfg.LogLevel = LogSeverity.Info;

                discordClient = new DiscordSocketClient(cfg);
                discordClient.Log += msg =>
                {
                    Console.WriteLine("[Discord] " + msg.ToString());
                    return Task.FromResult(0);
                };

                await discordClient.LoginAsync(TokenType.Bot, discordToken);
                await discordClient.StartAsync();

                Console.WriteLine("[Discord] Bot connected successfully.");
                string startMsg =
                    $"**Speeder startup complete and connected to Run8.**\n" +
                    $"AlertSpeed = {alertSpeed}\n" +
                    $"OverSpeed = {overSpeed}\n" +
                    $"AlertSpeedTimer = {alertSpeedTimer}s\n" +
                    $"HardCoupleSpeed = {hardCoupleSpeed} MPH\n" +
                    $"Trona = {tronaAlertSpeed}\n" +
                    $"SuperC = {superCAlertSpeed}";
                await DiscordSendAsync(discordStatusChannel, startMsg);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[Discord] Failed to connect: " + ex.Message);
                discordEnabled = false;
            }
        }

        private static async Task DiscordSendAsync(ulong channelId, string msg)
        {
            if (!discordEnabled || discordClient == null) return;
            try
            {
                IMessageChannel ch = discordClient.GetChannel(channelId) as IMessageChannel;
                if (ch != null)
                    await ch.SendMessageAsync(msg);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[Discord] Send failed: " + ex.Message);
            }
        }
        private static void OnConnected(object s, EventArgs e)
        {
            lock (lockObj) { isConnected = true; hasWarnedNoRun8 = false; hasReceivedData = false; startupComplete = false; }
            Console.WriteLine("[" + DateTime.Now.ToString("T") + "] Run8 instance detected.");
        }

        private static void OnDisconnected(object s, EventArgs e)
        {
            lock (lockObj)
            {
                isConnected = false;
                hasReceivedData = false;
                startupComplete = false;
                Console.WriteLine("[" + DateTime.Now.ToString("T") + "] Disconnected from Run8.");
            }
        }

        private static void OnSimulationState(object s, SimulationStateEventArgs e)
        {
            lock (lockObj)
            {
                lastSimTime = e.SimulationTime;
                hasReceivedData = true;
                if (!startupComplete)
                {
                    startupComplete = true;
                    Console.WriteLine("Startup complete.\n");
                    if (discordEnabled)
                        Task.Run(() => DiscordSendAsync(discordStatusChannel, "Speeder startup complete and connected to Run8."));
                }
            }
        }

        private static void OnTrainData(object s, TrainDataEventArgs e)
        {
            lock (lockObj)
            {
                dynamic train = e.Train;
                int id = train.TrainID;
                DateTime simNow = lastSimTime == DateTime.MinValue ? DateTime.Now : lastSimTime;
                EEngineerType current = (EEngineerType)train.EngineerType;
                if (!lastEngineerType.TryGetValue(id, out var prev)) prev = current;

                // Relinquish
                if (prev == EEngineerType.Player && current != EEngineerType.Player)
                {
                    string name = lastPlayerName.ContainsKey(id) ? lastPlayerName[id] : (string)train.EngineerName;
                    string sym = lastTrainSymbol.ContainsKey(id) ? lastTrainSymbol[id] : (string)train.TrainSymbol;
                    string msg = $"[{simNow:T}] {name} relinquished control of {sym}.";
                    Console.WriteLine(msg);
                    if (discordEnabled) Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                    activePlayers.Remove(id); speedingStart.Remove(id); maxOverspeed.Remove(id);
                    overSpeedWarned.Remove(id); sustainedWarned.Remove(id);
                    lastAxleCount.Remove(id); lastSpeed.Remove(id);
                    lastPlayerName.Remove(id); lastTrainSymbol.Remove(id);
                }

                // Player trains
                if (current == EEngineerType.Player)
                {
                    string eng = train.EngineerName; if (!string.IsNullOrWhiteSpace(eng)) lastPlayerName[id] = eng;
                    string sym = train.TrainSymbol; if (!string.IsNullOrWhiteSpace(sym)) lastTrainSymbol[id] = sym;

                    double curSpeed = train.TrainSpeedMph;
                    double lastKnown = lastSpeed.ContainsKey(id) ? lastSpeed[id] : curSpeed;
                    lastSpeed[id] = curSpeed;

                    int axles = train.AxleCount;
                    if (lastAxleCount.ContainsKey(id) && axles > lastAxleCount[id])
                    {
                        string msg = $"[{simNow:T}] {eng} on {sym} coupled at {lastKnown:F1} MPH";
                        Console.WriteLine(msg);
                        if (discordEnabled)
                        {
                            if (lastKnown <= hardCoupleSpeed)
                            {
                                Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                            }
                            else
                            {
                                Task.Run(() => DiscordSendAsync(discordAlertChannel, msg));
                                Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                            }
                        }
                    }
                    lastAxleCount[id] = axles;

                    if (!activePlayers.ContainsKey(id))
                    {
                        activePlayers[id] = simNow;
                        string msg = $"[{simNow:T}] {eng} took control of {sym}, Loco: {train.RailroadInitials} {train.LocoNumber}, TrainID: {id}";
                        Console.WriteLine(msg);
                        if (discordEnabled) Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                    }
                    else activePlayers[id] = simNow;

                    HandleSpeeding(train, id, simNow);
                }

                lastEngineerType[id] = current;
            }
        }

        private static void HandleSpeeding(dynamic train, int id, DateTime simNow)
        {
            double current = train.TrainSpeedMph;
            double limit = train.TrainSpeedLimitMPH;
            double curAbs = Math.Abs(current);
            double limAbs = Math.Abs(limit);
            double overNow = curAbs - limAbs;

            // Adjust effective limit instead of alert speed
            double effectiveLimit = limAbs;
            string symUp = ((string)train.TrainSymbol).ToUpperInvariant();
            int blk = (int)train.BlockID;
            string[] superList = superCTrainSymbols.Split(',').Select(x => x.Trim().ToUpperInvariant()).ToArray();

            bool isSuper = superList.Any(s => symUp.Contains(s));
            bool isTrona = blk.ToString().StartsWith(tronaRouteID.ToString()) && Math.Abs(train.TrainSpeedLimitMPH - 25);

            if (isSuper) effectiveLimit += superCAlertSpeed;
            else if (isTrona) effectiveLimit += tronaAlertSpeed;

            bool wasSpeed = speedingStart.ContainsKey(id);
            bool isSpeed = curAbs > effectiveLimit + alertSpeed;
            bool stopSpeed = wasSpeed && curAbs < effectiveLimit + alertSpeed - 1.0;

            if (isSpeed)
            {
                if (!wasSpeed)
                {
                    speedingStart[id] = simNow; maxOverspeed[id] = 0; sustainedWarned.Remove(id);
                    string msg = $"[{simNow:T}] {train.EngineerName}, {train.TrainSymbol}, {id} began speeding in block {train.BlockID}. ({current:F1}/{limit:F1} MPH)";
                    Console.WriteLine(msg);
                    if (discordEnabled) Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                }

                if (maxOverspeed.ContainsKey(id)) maxOverspeed[id] = Math.Max(maxOverspeed[id], overNow);

                if (curAbs > effectiveLimit + overSpeed && !overSpeedWarned.Contains(id))
                {
                    string msg = $"[{simNow:T}] {train.EngineerName}, {train.TrainSymbol} needs to be banned for speeding {overNow:F1} MPH over in block {train.BlockID}. ({current:F1}/{limit:F1})";
                    Console.WriteLine(msg);
                    if (discordEnabled) Task.Run(() => DiscordSendAsync(discordAlertChannel, msg));
                    overSpeedWarned.Add(id);
                }
                else if (wasSpeed && !sustainedWarned.Contains(id) && (simNow - speedingStart[id]).TotalSeconds > alertSpeedTimer)
                {
                    string msg = $"[{simNow:T}] {train.EngineerName}, {train.TrainSymbol} needs to be banned for sustained speeding ({alertSpeedTimer / 60.0:F1} minutes above the limit) in block {train.BlockID}.";
                    Console.WriteLine(msg);
                    if (discordEnabled) Task.Run(() => DiscordSendAsync(discordAlertChannel, msg));
                    sustainedWarned.Add(id);
                }
            }
            else if (stopSpeed)
            {
                DateTime start = speedingStart[id];
                double dur = (simNow - start).TotalSeconds;
                double maxOver = maxOverspeed.ContainsKey(id) ? maxOverspeed[id] : 0;
                string msg = $"[{simNow:T}] {train.EngineerName}, {train.TrainSymbol} is no longer speeding in block {train.BlockID}. Duration: ({dur / 60.0:F1} minutes, Speed limit exceeded by: {maxOver:F1} MPH.)";
                Console.WriteLine(msg);
                if (discordEnabled)
                {
                    Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                    if (overSpeedWarned.Contains(id) || sustainedWarned.Contains(id))
                        Task.Run(() => DiscordSendAsync(discordAlertChannel, msg));
                }
                speedingStart.Remove(id); maxOverspeed.Remove(id); overSpeedWarned.Remove(id); sustainedWarned.Remove(id);
            }
        }

        private static void MonitorPlayerTrains()
        {
            const int timeout = 2;
            while (true)
            {
                Thread.Sleep(1000);
                lock (lockObj)
                {
                    DateTime simNow = lastSimTime == DateTime.MinValue ? DateTime.Now : lastSimTime;
                    var stale = activePlayers.Where(k => (simNow - k.Value).TotalSeconds > timeout).Select(k => k.Key).ToList();
                    foreach (int id in stale)
                    {
                        string msg = $"[{simNow:T}] Player train {id} no longer reporting data.";
                        Console.WriteLine(msg);
                        if (discordEnabled) Task.Run(() => DiscordSendAsync(discordStatusChannel, msg));
                        activePlayers.Remove(id);
                        speedingStart.Remove(id); maxOverspeed.Remove(id); overSpeedWarned.Remove(id);
                        sustainedWarned.Remove(id); lastAxleCount.Remove(id); lastSpeed.Remove(id);
                    }
                }
            }
        }
    }
}

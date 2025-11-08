"""
R8Speeder - Player Train Speed Monitor for Run8 (Python)
Faithful C#-equivalent output and verified DispatcherComms connection.
"""

import os
import sys
import json
import threading
import time
import datetime
import asyncio
from typing import Dict, Set

# ========= .NET / Run8 bridging =========
try:
    import clr
except ImportError:
    print("pythonnet is required. Install with: pip install pythonnet==3.0.3")
    sys.exit(1)

# ========= Settings =========
SETTINGS_FILE = "SpeederSettings.json"
lock_obj = threading.Lock()

# Data stores
active_players: Dict[int, datetime.datetime] = {}
speeding_start: Dict[int, datetime.datetime] = {}
max_overspeed: Dict[int, float] = {}
overspeed_warned: Set[int] = set()
sustained_warned: Set[int] = set()
last_axle_count: Dict[int, int] = {}
last_speed: Dict[int, float] = {}
axle_increase_blocked_until: Dict[int, datetime.datetime] = {}
last_engineer_type: Dict[int, int] = {}
last_player_name: Dict[int, str] = {}
last_train_symbol: Dict[int, str] = {}
speed_exceed_start: Dict[int, datetime.datetime] = {}

# State variables
last_sim_time = datetime.datetime.min
is_connected = False
has_permission = False

# Defaults
alert_speed = 5.0
over_speed = 20.0
alert_speed_timer = 300
hard_couple_speed = 7.0
trona_alert_speed = 20.0
trona_route_id = 320
superc_alert_speed = 25.0
superc_train_symbols = "991,981,119,198,Super"

dispatcher_comms_path = None
discord_enabled = False
discord_token = ""
discord_alert_channel = 0
discord_alert_role=""
discord_status_channel = 0

# Objects
mRun8 = None
DispatcherProxyFactory = None
Run8ProxyFactory = None
EEngineerType = None
discord_client = None
discord_loop = None

# Constants
SPEED_CONFIRMATION_SECONDS = 5.0
AXLE_BLOCK_DURATION = datetime.timedelta(seconds=5)
DISPATCHER_RADIO_CHANNEL = 0


# =========================================================
# SETTINGS
# =========================================================
def load_settings():
    global alert_speed, over_speed, alert_speed_timer, hard_couple_speed
    global trona_alert_speed, trona_route_id, superc_alert_speed, superc_train_symbols
    global dispatcher_comms_path, discord_enabled, discord_token
    global discord_alert_channel, discord_status_channel

    if not os.path.exists(SETTINGS_FILE):
        return

    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return

    alert_speed = float(data.get("AlertSpeed", alert_speed))
    speeding_start_msg = data.get("SpeedingStartMsg", speeding_start_msg)
    speeding_end_msg = data.get("SpeedingEndMsg", speeding_end_msg)
    over_speed = float(data.get("OverSpeed", over_speed))
    over_speed_ban_msg = data.get("OvrSpeedBanMsg", over_speed_ban_msg)
    alert_speed_timer = int(data.get("AlertSpeedTimer", alert_speed_timer))
    sustained_speed_ban_msg = data.get("SustSpeedBanMsg", sustained_speed_ban_msg)
    hard_couple_speed = float(data.get("HardCoupleSpeed", hard_couple_speed))
    trona_alert_speed = float(data.get("TronaAlertSpeed", trona_alert_speed))
    trona_route_id = int(data.get("TronaRouteID", trona_route_id))
    superc_alert_speed = float(data.get("SuperCAlertSpeed", superc_alert_speed))
    superc_train_symbols = data.get("SuperCTrainSymbols", superc_train_symbols)
    dispatcher_comms_path = data.get("DispatcherCommsPath", dispatcher_comms_path)
    verbose_logging = bool(data.get("VerboseLogging", verbose_logging)

    discord_enabled = bool(data.get("DiscordEnabled", discord_enabled))
    discord_token = data.get("DiscordBotToken", discord_token)
    discord_self_name = data.get("DiscordSelfName", discord_self_name)
    discord_alert_channel = int(data.get("DiscordAlertChannel", discord_alert_channel))
    discord_alert_role = data.get("DiscordAlertRole", discord_alert_role)
    discord_status_channel = int(data.get("DiscordStatusChannel", discord_status_channel))

    if dispatcher_comms_path:
        dispatcher_comms_path = os.path.expandvars(dispatcher_comms_path)
        if not os.path.isabs(dispatcher_comms_path):
            dispatcher_comms_path = os.path.abspath(dispatcher_comms_path)


# =========================================================
# DLL LOADING
# =========================================================
def load_dispatcher_comms():
    global DispatcherProxyFactory, Run8ProxyFactory, EEngineerType
    dll_path = dispatcher_comms_path or r"F:\Games\Run8\DispatcherComms.dll"
    clr.AddReference(dll_path)
    import DispatcherComms
    from DispatcherComms import Run8ProxyFactory, DispatcherProxyFactory, MessagesFromRun8
    globals()["Run8ProxyFactory"] = Run8ProxyFactory
    globals()["DispatcherProxyFactory"] = DispatcherProxyFactory
    globals()["EEngineerType"] = getattr(MessagesFromRun8, "EEngineerType", None)


# =========================================================
# DISCORD INTEGRATION
# =========================================================
async def discord_start():
    import discord
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    async def on_ready():
        print("[Discord] Bot connected successfully.")
        if discord_status_channel:
            ch = client.get_channel(discord_status_channel)
            if ch:
                await ch.send(discord_self_name + " connected to Run8 and is monitoring trains.")

    client.event(on_ready)
    globals()["discord_client"] = client

    try:
        await client.start(discord_token)
    except Exception:
        globals()["discord_client"] = None


def start_discord_in_thread():
    if not discord_enabled or not discord_token:
        return

    def runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        globals()["discord_loop"] = loop
        loop.run_until_complete(discord_start())

    threading.Thread(target=runner, daemon=True).start()


def discord_send(channel_id: int, msg: str):
    if not discord_enabled or discord_client is None or discord_loop is None:
        return

    async def _send():
        ch = discord_client.get_channel(channel_id)
        if ch:
            await ch.send(msg)

    asyncio.run_coroutine_threadsafe(_send(), discord_loop)


# =========================================================
# EVENT HANDLERS
# =========================================================
def on_connected(sender, args):
    global is_connected
    is_connected = True
    print(f"[{datetime.datetime.now().time()}] Run8 instance detected. Waiting on 'Allow External DS'")


def on_disconnected(sender, args):
    global is_connected
    is_connected = False
    print(f"[{datetime.datetime.now().time()}] Disconnected from Run8.")


def on_dispatcher_permission(sender, args):
    global has_permission
    permission_str = str(args.Permission)
    has_permission = (permission_str == "Granted")


def on_simulation_state(sender, args):
    global last_sim_time
    last_sim_time = args.SimulationTime


def send_zero_speed_limit_radio_if_needed(train):
    if not mRun8:
        return
    try:
        limit = int(train.TrainSpeedLimitMPH)
        if limit == 0:
            msg = f"{train.EngineerName}, briefly relinquish your train to fix a 0mph speed limit error. This is an automated message."
            mRun8.SendRadioText(DISPATCHER_RADIO_CHANNEL, msg)
    except Exception:
        pass


def handle_speeding(train, train_id: int, sim_now: datetime.datetime):
    current = float(train.TrainSpeedMph)
    limit = float(train.TrainSpeedLimitMPH)
    cur_abs, lim_abs = abs(current), abs(limit)
    effective_limit = lim_abs
    sym = str(train.TrainSymbol).upper()
    blk = int(train.BlockID)
    is_super = any(s in sym for s in [x.strip().upper() for x in superc_train_symbols.split(",")])
    is_trona = str(blk).startswith(str(trona_route_id)) and limit == 25.0

    if is_super:
        effective_limit = superc_alert_speed + limit
    elif is_trona:
        effective_limit = trona_alert_speed + limit

    was_speeding = train_id in speeding_start
    above_alert = cur_abs > (effective_limit + alert_speed)
    above_over = cur_abs > (effective_limit + over_speed)
    stop_speeding = was_speeding and cur_abs < (effective_limit + alert_speed - 1.0)

    if above_alert:
#Speeding start
        if train_id not in speed_exceed_start:
            speed_exceed_start[train_id] = sim_now

        if (not was_speeding) and (sim_now - speed_exceed_start[train_id]).total_seconds() >= SPEED_CONFIRMATION_SECONDS:
            speeding_start[train_id] = sim_now
            max_overspeed[train_id] = 0.0
            if train_id in sustained_warned:
                sustained_warned.remove(train_id)
            print(speeding_start_msg)
            if discord_enabled and discord_status_channel:
                discord_send(discord_status_channel, speeding_start_msg)

        if was_speeding and train_id in max_overspeed:
            over_now = cur_abs - lim_abs
            if over_now > max_overspeed[train_id]:
                max_overspeed[train_id] = over_now

#Excessive speed detect/warn
        if above_over and train_id not in overspeed_warned:
            print(over_speed_ban_msg)
            if discord_enabled and discord_alert_channel and discord_alert_role:
                tban_msg = "<@&" + discord_alert_role + "> - " + over_speed_ban_msg)
                discord_send(discord_alert_channel, tban_msg)
            elif discord_enabled and discord_alert_channel:
                discord_send(discord_alert_channel, over_speed_ban_msg)
            overspeed_warned.add(train_id)

#Sustained speed detect/warn
        if was_speeding and train_id not in sustained_warned:
            dur = (sim_now - speeding_start[train_id]).total_seconds()
            if dur > alert_speed_timer:
                print(sustained_speed_ban_msg)
                if discord_enabled and discord_alert_channel:
                    discord_send(discord_alert_channel, sustained_speed_ban_msg)
                sustained_warned.add(train_id)
    else:
        if train_id in speed_exceed_start:
            del speed_exceed_start[train_id]
#Speeding end
        if stop_speeding:
            start = speeding_start[train_id]
            dur = (sim_now - start).total_seconds()
            max_over = max_overspeed.get(train_id, 0.0)
            print(speeding_end_msg)
            if discord_enabled and discord_status_channel:
                discord_send(discord_status_channel, speeding_end_msg)
                if (train_id in overspeed_warned) or (train_id in sustained_warned):
                    if discord_alert_channel:
                        discord_send(discord_alert_channel, speeding_end_msg)
            speeding_start.pop(train_id, None)
            max_overspeed.pop(train_id, None)
            overspeed_warned.discard(train_id)
            sustained_warned.discard(train_id)


def on_train_data(sender, e):
    train = e.Train
    train_id = int(train.TrainID)
    sim_now = last_sim_time if last_sim_time != datetime.datetime.min else datetime.datetime.now()
    with lock_obj:
        current_engineer_type = int(train.EngineerType)
        previous_engineer_type = last_engineer_type.get(train_id, current_engineer_type)

        if previous_engineer_type == int(EEngineerType.Player) and current_engineer_type != int(EEngineerType.Player):
            engineer = last_player_name.get(train_id, str(train.EngineerName))
            symbol = last_train_symbol.get(train_id, str(train.TrainSymbol))
            
            if verbose_logging:
                msg = f"[{sim_now.time()}] {engineer} relinquished control of {symbol}."
                print(msg)
                if discord_enabled and discord_status_channel:
                    discord_send(discord_status_channel, msg)

            for d in [active_players, speeding_start, max_overspeed, last_axle_count, last_speed,
                      axle_increase_blocked_until, last_player_name, last_train_symbol, speed_exceed_start]:
                d.pop(train_id, None)
            overspeed_warned.discard(train_id)
            sustained_warned.discard(train_id)

        if current_engineer_type == int(EEngineerType.Player):
            last_player_name[train_id] = str(train.EngineerName)
            last_train_symbol[train_id] = str(train.TrainSymbol)
            current_speed = float(train.TrainSpeedMph)
            last_speed[train_id] = current_speed
            axle_count = int(train.AxleCount)
            last_axle_count[train_id] = axle_count

            if train_id not in active_players:
                active_players[train_id] = sim_now
                send_zero_speed_limit_radio_if_needed(train)

                if verbose_logging:
                    msg = (f"[{sim_now.time()}] {train.EngineerName} took control of {train.TrainSymbol}, "
                           f"Loco: {train.RailroadInitials} {train.LocoNumber}, TrainID: {train.TrainID}")
                    print(msg)

                    if discord_enabled and discord_status_channel:
                        discord_send(discord_status_channel, msg)

            else:
                active_players[train_id] = sim_now

            handle_speeding(train, train_id, sim_now)

        last_engineer_type[train_id] = current_engineer_type


# =========================================================
# MONITOR THREAD
# =========================================================
def monitor_player_trains():
    while True:
        time.sleep(1)
        sim_now = last_sim_time if last_sim_time != datetime.datetime.min else datetime.datetime.now()
        stale = [tid for tid, ts in active_players.items() if (sim_now - ts).total_seconds() > 5]
        for tid in stale:
            if verbose_logging:
                msg = f"[{sim_now.time()}] Player train {tid} no longer reporting data."
                print(msg)
                if discord_enabled and discord_status_channel:
                    discord_send(discord_status_channel, msg)
            for d in [active_players, speeding_start, max_overspeed, last_axle_count, last_speed,
                      axle_increase_blocked_until, last_player_name, last_train_symbol, speed_exceed_start]:
                d.pop(tid, None)
            overspeed_warned.discard(tid)
            sustained_warned.discard(tid)


# =========================================================
# MAIN
# =========================================================
def main():
    global mRun8
    print("=== R8Speeder (Python) ===")
    print("Attempting to connect to Run8 External Dispatcher Interface...")
    print("Press CTRL+C to exit at any time.\n")

    load_settings()
    load_dispatcher_comms()
    start_discord_in_thread()

    mRun8 = Run8ProxyFactory.GetRun8Proxy()
    mRun8.Connected += on_connected
    mRun8.Disconnected += on_disconnected
    mRun8.TrainData += on_train_data
    mRun8.SimulationState += on_simulation_state
    try:
        mRun8.DispatcherPermission += on_dispatcher_permission
    except Exception:
        pass

    port = DispatcherProxyFactory.DefaultExternalDispatcherPort
    mRun8.Start("localhost", port)
    threading.Thread(target=monitor_player_trains, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()

import os
import sys
import json
import threading
import time
import asyncio
from typing import Dict, Set

try:
    import clr
except ImportError:
    print("pythonnet is required. Install with: pip install pythonnet==3.0.3")
    sys.exit(1)

# ============ GLOBALS ============
SETTINGS_FILE = "SpeederSettings.json"
lock_obj = threading.Lock()

# Data stores
active_players: Dict[int, object] = {}
speeding_start: Dict[int, object] = {}
max_overspeed: Dict[int, float] = {}
overspeed_warned: Set[int] = set()
sustained_warned: Set[int] = set()
last_axle_count: Dict[int, int] = {}
last_speed: Dict[int, float] = {}
axle_increase_blocked_until: Dict[int, object] = {}
last_engineer_type: Dict[int, int] = {}
last_player_name: Dict[int, str] = {}
last_train_symbol: Dict[int, str] = {}
speed_exceed_start: Dict[int, object] = {}
prev_speed_snapshot: Dict[int, float] = {}
zero_limit_pending: Dict[int, float] = {}
zero_limit_announced: Set[int] = set()

# State variables
last_sim_time = None
is_connected = False
has_permission = False
last_data_received_ts = None
data_timeout_announced = False

# Settings variables
alert_speed = over_speed = alert_speed_timer = hard_couple_speed = 0
trona_alert_speed = trona_route_id = superc_alert_speed = 0
superc_train_symbols = ""
dispatcher_comms_path = ""
discord_enabled = False
discord_token = ""
discord_alert_channel = 0
discord_status_channel = 0
periodic_announce_time = 0
messages = {}

# .NET and Discord objects
mRun8 = None
DispatcherProxyFactory = None
Run8ProxyFactory = None
EEngineerType = None
discord_client = None
discord_loop = None
startup_complete_announced = False

SPEED_CONFIRMATION_SECONDS = 5.0
AXLE_BLOCK_DURATION_SECONDS = 5
DISPATCHER_RADIO_CHANNEL = 0


# =========================================================
# SETTINGS
# =========================================================
def load_settings():
    global alert_speed, over_speed, alert_speed_timer, hard_couple_speed, verbose_logging
    global trona_alert_speed, trona_route_id, superc_alert_speed, superc_train_symbols
    global dispatcher_comms_path, discord_enabled, discord_token, discord_alert_role
    global discord_alert_channel, discord_status_channel, messages, periodic_announce_time

    with open(SETTINGS_FILE, "r") as f:
        data = json.load(f)

    alert_speed = float(data["AlertSpeed"])
    over_speed = float(data["OverSpeed"])
    alert_speed_timer = int(data["AlertSpeedTimer"])
    hard_couple_speed = float(data["HardCoupleSpeed"])
    verbose_logging = float(data["VerboseLogging"])
    trona_alert_speed = float(data["TronaAlertSpeed"])
    trona_route_id = int(data["TronaRouteID"])
    superc_alert_speed = float(data["SuperCAlertSpeed"])
    superc_train_symbols = data["SuperCTrainSymbols"]
    dispatcher_comms_path = data["DispatcherCommsPath"]
    periodic_announce_time = data["PeriodicAnnounceTimer"]

    discord_enabled = bool(data["DiscordEnabled"])
    discord_token = data["DiscordBotToken"]
    discord_alert_channel = int(data["DiscordAlertChannel"])
    discord_status_channel = int(data["DiscordStatusChannel"])
    discord_alert_role = int(data["DiscordAlertRole"])

    messages = data["Messages"]  # full dictionary of message templates


# =========================================================
# DLL LOADING
# =========================================================
def load_dispatcher_comms():
    global DispatcherProxyFactory, Run8ProxyFactory, EEngineerType
    dll_path = os.path.expandvars(dispatcher_comms_path)
    clr.AddReference(dll_path)
    import DispatcherComms
    from DispatcherComms import Run8ProxyFactory, DispatcherProxyFactory, MessagesFromRun8
    globals()["Run8ProxyFactory"] = Run8ProxyFactory
    globals()["DispatcherProxyFactory"] = DispatcherProxyFactory
    globals()["EEngineerType"] = getattr(MessagesFromRun8, "EEngineerType", None)


# =========================================================
# DISCORD
# =========================================================
def announce_startup_complete():
    """Emit the startup-complete message once train data is confirmed."""
    global startup_complete_announced
    if startup_complete_announced:
        return
    msg = messages.get("StartupCompleteMsg")
    if msg:
        print(msg)
        if discord_enabled and discord_status_channel:
            discord_send(discord_status_channel, msg)
    startup_complete_announced = True


async def discord_start():
    import discord
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    async def on_ready():
        print("[Discord] Speeder connected to Discord successfully.")

    client.event(on_ready)
    globals()["discord_client"] = client

    await client.start(discord_token)


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


def discord_broadcast_alert(msg: str):
    """Send alert-level messages to both alert and status channels when available."""
    if not discord_enabled:
        return
    if discord_alert_channel:
        discord_send(discord_alert_channel, msg)
    if discord_status_channel:
        discord_send(discord_status_channel, msg)


# =========================================================
# EVENT HANDLERS
# =========================================================
def on_connected(sender, args):
    global is_connected
    is_connected = True
    stamp = str(last_sim_time) if last_sim_time else time.strftime("%H:%M:%S")
    msg = messages.get("ConnectedMsg")
    if msg:
        formatted = msg.format(stamp=stamp)
        print(formatted)
        if discord_enabled and discord_status_channel:
            discord_send(discord_status_channel, formatted)


def on_disconnected(sender, args):
    global is_connected
    is_connected = False
    emit_disconnected_message()




def on_dispatcher_permission(sender, args):
    global has_permission
    has_permission = str(args.Permission) == "Granted"


def on_simulation_state(sender, args):
    global last_sim_time
    last_sim_time = args.SimulationTime


# =========================================================
# MESSAGE HELPERS
# =========================================================
def format_msg(key, **kwargs):
    if key not in messages:
        return "*ERROR: SpeederSettings.json key is not in messages*"
    try:
        return messages[key].format(**kwargs)
    except Exception:
        return "*ERROR: An exception has occurred during message formatting. See the console for more details.*"


def emit_disconnected_message():
    """Send the standard disconnected message to terminal and Discord."""
    global data_timeout_announced
    stamp = str(last_sim_time) if last_sim_time else time.strftime("%H:%M:%S")
    msg = messages.get("DisconnectedMsg")
    if not msg:
        return
    formatted = msg.format(stamp=stamp)
    print(formatted)
    if discord_enabled and discord_status_channel:
        discord_send(discord_status_channel, formatted)
    data_timeout_announced = True


# =========================================================
# TRAIN / RADIO / SPEEDING
# =========================================================
def send_zero_speed_limit_radio_if_needed(train):
    global zero_limit_pending, zero_limit_announced
    if not mRun8:
        return
    
    try:
        limit = int(train.TrainSpeedLimitMPH)
    except Exception:
        limit = 0
    hp_per_ton = float(train.HpPerTon)
    train_id = int(getattr(train, "TrainID", 0))
    now = time.time()

    if hp_per_ton <= 0 or limit != 0:
        zero_limit_pending.pop(train_id, None)
        zero_limit_announced.discard(train_id)
        return

    first_seen = zero_limit_pending.get(train_id)
    if first_seen is None:
        zero_limit_pending[train_id] = now
        return

    if (now - first_seen) < 3.0 or train_id in zero_limit_announced:
        return

    zero_limit_pending.pop(train_id, None)
    notice_template = messages.get("AutomatedNoticeMsg")
    zero_template = messages.get("ZeroLimitMsg")

    if notice_template:
        notice_msg = notice_template.format(train=train)
        if notice_msg:
            mRun8.SendRadioText(DISPATCHER_RADIO_CHANNEL, notice_msg)

    if zero_template:
        zero_msg = zero_template.format(train=train)
        if zero_msg:
            mRun8.SendRadioText(DISPATCHER_RADIO_CHANNEL, zero_msg)

    zero_limit_announced.add(train_id)


def handle_speeding(train, train_id, sim_now):
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

    # Speeding start
    if above_alert:
        if train_id not in speed_exceed_start:
            speed_exceed_start[train_id] = sim_now

        if (not was_speeding) and (sim_now.Subtract(speed_exceed_start[train_id]).TotalSeconds >= SPEED_CONFIRMATION_SECONDS):
            speeding_start[train_id] = sim_now
            max_overspeed[train_id] = 0.0
            msg = format_msg(
                "SpeedingStartMsg",
                sim_now=sim_now,
                train=train,
                train_id=train_id,
                current=current,
                limit=limit,
                block=train.BlockID
            )
            print(msg)
            if discord_enabled and discord_status_channel:
                discord_send(discord_status_channel, msg)

        if was_speeding and train_id in max_overspeed:
            over_now = cur_abs - lim_abs
            if over_now > max_overspeed[train_id]:
                max_overspeed[train_id] = over_now

        if above_over and train_id not in overspeed_warned:
            msg = format_msg(
                "OvrSpeedBanMsg",
                sim_now=sim_now, train=train, train_id=train_id,
                current=current, limit=limit, block=train.BlockID,
                over=(cur_abs - lim_abs)
            )
            print(msg)
            if discord_enabled:
                if discord_alert_role != 0 and discord_alert_channel:
                    if discord_status_channel:
                        discord_send(discord_status_channel, msg)
                    msg = "<@&" + str(discord_alert_role) + "> - " + msg
                    discord_send(discord_alert_channel, msg)
                else:
                    discord_broadcast_alert(msg)
            overspeed_warned.add(train_id)

        if was_speeding and train_id not in sustained_warned:
            dur = sim_now.Subtract(speeding_start[train_id]).TotalSeconds
            if dur > alert_speed_timer:
                msg = format_msg(
                    "SustSpeedBanMsg",
                    sim_now=sim_now, train=train, train_id=train_id,
                    current=current, limit=limit, block=train.BlockID,
                    minutes=alert_speed_timer / 60.0
                )
                print(msg)
                discord_broadcast_alert(msg)
                sustained_warned.add(train_id)
    else:
        if train_id in speed_exceed_start:
            del speed_exceed_start[train_id]
        if stop_speeding:
            start = speeding_start[train_id]
            dur = sim_now.Subtract(start).TotalSeconds
            max_over = max_overspeed.get(train_id, 0.0)
            msg = format_msg(
                "SpeedingEndMsg",
                sim_now=sim_now,
                train=train,
                train_id=train_id,
                duration=dur / 60.0,
                max_over=max_over,
                block=train.BlockID
            )
            print(msg)
            if discord_enabled:
                if discord_status_channel:
                    discord_send(discord_status_channel, msg)
                if discord_alert_channel and (train_id in overspeed_warned or train_id in sustained_warned):
                    discord_send(discord_alert_channel, msg)
            speeding_start.pop(train_id, None)
            max_overspeed.pop(train_id, None)
            overspeed_warned.discard(train_id)
            sustained_warned.discard(train_id)


# =========================================================
# COUPLING DETECTION
# =========================================================
def handle_coupling(train, train_id, sim_now):
    current_axles = int(train.AxleCount)

    # Initialize if first observation
    if train_id not in last_axle_count:
        last_axle_count[train_id] = current_axles
        prev_speed_snapshot[train_id] = abs(float(train.TrainSpeedMph))
        return

    previous_axles = last_axle_count[train_id]
    previous_speed = abs(float(prev_speed_snapshot.get(train_id, train.TrainSpeedMph)))

    # Skip if axle count unchanged
    if current_axles == previous_axles:
        prev_speed_snapshot[train_id] = abs(float(train.TrainSpeedMph))
        return

    # Axle decrease → block next 5 seconds
    if current_axles < previous_axles:
        axle_increase_blocked_until[train_id] = sim_now.AddSeconds(AXLE_BLOCK_DURATION_SECONDS)
        last_axle_count[train_id] = current_axles
        prev_speed_snapshot[train_id] = abs(float(train.TrainSpeedMph))
        return

    # If blocked, ignore
    if train_id in axle_increase_blocked_until:
        blocked_until = axle_increase_blocked_until[train_id]
        if sim_now.Subtract(blocked_until).TotalSeconds < 0:
            last_axle_count[train_id] = current_axles
            prev_speed_snapshot[train_id] = abs(float(train.TrainSpeedMph))
            return
        else:
            axle_increase_blocked_until.pop(train_id, None)

    # Coupling detected (axle increase)
    if current_axles > previous_axles:
        axle_increase_blocked_until[train_id] = sim_now.AddSeconds(AXLE_BLOCK_DURATION_SECONDS)
        msg = format_msg(
            "CoupledMsg",
            sim_now=sim_now,
            train=train,
            prev_axles=previous_axles,
            curr_axles=current_axles,
            speed=previous_speed
        )
        if msg:
            print(msg)
            if discord_enabled:
                if discord_status_channel and verbose_logging:
                    discord_send(discord_status_channel, msg)
                if previous_speed > hard_couple_speed:
                    if discord_alert_channel:
                        discord_send(discord_alert_channel, msg)
                    if not verbose_logging:
                        discord_send(discord_status_channel, msg)

    # Update tracking
    last_axle_count[train_id] = current_axles
    prev_speed_snapshot[train_id] = abs(float(train.TrainSpeedMph))






# =========================================================
# TRAIN DATA HANDLER
# =========================================================
def on_train_data(sender, e):
    global last_data_received_ts, data_timeout_announced
    train = e.Train
    train_id = int(train.TrainID)
    last_data_received_ts = time.time()
    data_timeout_announced = False
    sim_now = last_sim_time
    if sim_now is None:
        return

    with lock_obj:
        announce_startup_complete()
        current_engineer_type = int(train.EngineerType)
        previous_engineer_type = last_engineer_type.get(train_id, current_engineer_type)

        if previous_engineer_type == int(EEngineerType.Player) and current_engineer_type != int(EEngineerType.Player):
            msg = format_msg("RelinquishMsg", sim_now=sim_now, train=train)
            print(msg)
            if discord_enabled and discord_status_channel and verbose_logging:
                discord_send(discord_status_channel, msg)
            for d in [active_players, speeding_start, max_overspeed, last_axle_count, last_speed,
                      axle_increase_blocked_until, last_player_name, last_train_symbol, speed_exceed_start,
                      zero_limit_pending]:
                d.pop(train_id, None)
            overspeed_warned.discard(train_id)
            sustained_warned.discard(train_id)
            zero_limit_announced.discard(train_id)

        if current_engineer_type == int(EEngineerType.Player):
            last_player_name[train_id] = str(train.EngineerName)
            last_train_symbol[train_id] = str(train.TrainSymbol)
            current_speed = float(train.TrainSpeedMph)
            last_speed[train_id] = current_speed

            if train_id not in active_players:
                active_players[train_id] = sim_now
                msg = format_msg("TookControlMsg", sim_now=sim_now, train=train)
                print(msg)
                if discord_enabled and discord_status_channel and verbose_logging:
                    discord_send(discord_status_channel, msg)
            else:
                active_players[train_id] = sim_now

            send_zero_speed_limit_radio_if_needed(train)
            handle_speeding(train, train_id, sim_now)
            handle_coupling(train, train_id, sim_now)
            last_speed[train_id] = current_speed

        last_engineer_type[train_id] = current_engineer_type


# =========================================================
# MONITOR THREAD
# =========================================================
def monitor_player_trains():
    import System
    global last_data_received_ts, data_timeout_announced
    periodic_announce_counter = periodic_announce_time
    periodic_announce_msg = messages.get("PeriodicAnnounceMsg")
    notice_msg = messages.get("AutomatedNoticeMsg")
    while True:
        time.sleep(1)
        now = time.time()
        if periodic_announce_counter == periodic_announce_time:
            mRun8.SendRadioText(DISPATCHER_RADIO_CHANNEL, notice_msg)
            mRun8.SendRadioText(DISPATCHER_RADIO_CHANNEL, periodic_announce_msg)
            periodic_announce_counter = 1
        periodic_announce_counter += 1
        if last_data_received_ts is not None and (now - last_data_received_ts) > 5:
            if not data_timeout_announced:
                emit_disconnected_message()

        if last_sim_time is None:
            continue

        sim_now = last_sim_time
        stale = []
        for tid, ts in list(active_players.items()):
            try:
                if sim_now.Subtract(ts).TotalSeconds > 5:
                    stale.append(tid)
            except Exception:
                continue

        for tid in stale:
            msg = format_msg("TrainTimeoutMsg", sim_now=sim_now, train_id=tid)
            print(msg)
            if discord_enabled and discord_status_channel and verbose_logging:
                discord_send(discord_status_channel, msg)
            for d in [active_players, speeding_start, max_overspeed, last_axle_count, last_speed,
                      axle_increase_blocked_until, last_player_name, last_train_symbol, speed_exceed_start,
                      zero_limit_pending]:
                d.pop(tid, None)
            overspeed_warned.discard(tid)
            sustained_warned.discard(tid)
            zero_limit_announced.discard(tid)


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

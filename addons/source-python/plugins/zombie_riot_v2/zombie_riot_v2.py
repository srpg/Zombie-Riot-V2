#   Python
from random import choice
from os import listdir
#	ConfigObj
from configobj import ConfigObj
#	Commands
from commands.say import SayCommand
from commands.server import ServerCommand
#   Core
from core import GAME_NAME, PLATFORM
#   Colors
from colors import Color, GREEN, RED, LIGHT_GREEN as BRIGHT_GREEN
#   Config
from config.manager import ConfigManager
#   Cvar
from cvars import cvar
#   Engine
from engines.server import engine_server, queue_command_string
from engines.precache import Model
from engines.sound import Sound
#	Events
from events import Event
#   Entity
from entities.entity import Entity
from entities.hooks import EntityPreHook, EntityCondition
#	Filters
from filters.players import PlayerIter
from filters.weapons import WeaponIter, WeaponClassIter
#	Path
from paths import Path
#	Player
from players.entity import Player
from players.helpers import index_from_userid
from players.constants import PlayerButtons
#   Mathlib
from mathlib import Vector
#	Messages
from messages import SayText2, HintText, TextMsg
#   Memory
from memory.hooks import PreHook
from memory import find_binary, Convention, DataType
#	Menus
from menus import SimpleMenu, SimpleOption, Text
from menus import PagedMenu, PagedOption
#   Listeners
from listeners import OnLevelShutdown, OnPlayerRunCommand, OnEntityCreated
from listeners.tick import Delay, Repeat
#   Weapon Restrict
from weapons.restrictions import WeaponRestrictionHandler
#   Stringtable
from stringtables.downloads import Downloadables
# Translations
from translations.strings import LangStrings
#=================================
# Globals
#=================================
day = 1
max_day = 1
zombies = 0

joined = []

freeze_delay = None
flash_delay = None
god_delay = None

_path = Path(__file__).dirname()
_server_name = cvar.find_var('hostname')

_translations = LangStrings('zombie_riot_v2')
_settings = ConfigObj(_path + '/settings.ini')
_downloads = _path.joinpath('downloads.txt')

prefix = f'{GREEN}[Zombie Riot] » {BRIGHT_GREEN}'

MARKET = SayText2(_translations['market'])
GAMEPLAY = SayText2(_translations['gameplay'])

RESPAWN = TextMsg('You will respawn in {time} seconds')
RESPAWNS = TextMsg('You will respawn in {time} second')

NO_NEXT_MAP_FOUND = SayText2(_translations['map no found'])
NEXT_MAP_SELECTED = SayText2(_translations['new map'])
MAP_CHANGE = SayText2(_translations['map change'])

MARKET_ALIVE = SayText2(_translations['market alive'])
MARKET_TEAM = SayText2(_translations['market ct'])

PURCHASE_ALIVE = SayText2(_translations['purchase alive'])
PURCHASE_AFFORD = SayText2(_translations['purchase afford'])
PURCHASE_TEAM = SayText2(_translations['purchase team'])
PURCHASED_SUCCESFULLY = SayText2(_translations['succesfully purchased'])

HINT_INFO = HintText('{title}\nDay: {day}/{max_day}\nHumans left: {humans}\nZombies left: {zombies}')
HINT_INFO_BOT = HintText('{title}\nDay: {day}/{max_day}\nHumans left: {humans}\nZombies left: {zombies}\n{name}: {health}')

MAP_LIST = listdir(f'{GAME_NAME}/maps')
BACKGROUND_SOUND = Sound('ambient/zr/zr_ambience.mp3')
ICE_SOUND = Sound('physics/glass/glass_impact_bullet1.wav')

#=================================
# Config
#=================================
with ConfigManager('zombie_riot') as zr_cvar:
    spawn_money = zr_cvar.cvar('zr_spawn_money', default=12000, description='How much players cash will be set when spawn')
    enable_hint_panel = zr_cvar.cvar('zr_enable_hint_panel', default=1, description='Enable/Disable hudinfo')
    enable_background_sound = zr_cvar.cvar('zr_background_sound', default=1, description='Enable/Disable background sound')
    enable_server_name = zr_cvar.cvar('zr_enable_server_name', default=1, description='Enable/Disable to change server name, displays current day and max day')
    server_name = zr_cvar.cvar('zr_server_name', default='Your server name here', description='The server name get set')
    enable_fire_grenade = zr_cvar.cvar('zr_fire_hegrenade', default=1, description='Should hegrenade ignite zombies')
    enable_freeze_flash = zr_cvar.cvar('zr_freeze_flashbang', default=1, description='Should flashbang freeze zombies')
    freeze_radius = zr_cvar.cvar('zr_flashbang_freeze_radius', default=300, description='The radius where zombies get frozen')
    freeze_duration = zr_cvar.cvar('zr_flashbang_freeze_duration', default=10, description='Duration of flashbang freeze')
    enable_smokegrenade_light = zr_cvar.cvar('zr_smokegrenade_light', default=1, description='Should smokegrenade make light area where it lands')
    enable_market = zr_cvar.cvar('zr_enable_market', default=1, description='Enable/Disable market')
    enable_random_map = zr_cvar.cvar('zr_enable_random_map_change', default=1, description='When all days have finished should server change new random map')
#=================================
# Loading & Downloads
#=================================

def load():
    if bool(enable_hint_panel):
        hint_panel.start(1)

    if bool(enable_background_sound):
        background.start(60)

    queue_command_string('bot_quota 20')
    queue_command_string('bot_join_after_player 0')
    queue_command_string('bot_join_team t')
    queue_command_string('bot_quota_mode off')
    queue_command_string('mp_limitteams 0')
    queue_command_string('mp_autoteambalance 0')
    queue_command_string('bot_chatter off')
    queue_command_string('mp_humanteam ct')
    queue_command_string('sv_hudhint_sound 0')
    queue_command_string('mp_timelimit 300')

    if bool(enable_server_name):
        _server_name.set_string(f'{server_name.get_string()}' + f'Day: {day}/{max_day}')

    dl = Downloadables()
    with open(_downloads, 'r', encoding='utf-8') as open_file:
        for line in open_file:
            line = line.strip()
            if not line:
                continue
            dl.add(line)

    end_round()
    for player in PlayerIter('bot'):
        player.switch_team(2)

def unload():
    if bool(enable_hint_panel):
        hint_panel.stop()

    if bool(enable_background_sound):
        background.stop()

#=================================
# Extended Player Class
#=================================
class ZRPlayer(Player):
    caching = True

    def __init__(self, index):
        super().__init__(index)
        self.hurted_zombie = None

    def respawn_human(self, count, total):
        index = self.index

        if not self.dead:
            return

        if not self.team == 3:
            return

        if zombies > 0 and alive_humans() > 0:

            count += 1
            if count < total:
                remaining_time = int(total - count)
                if remaining_time > 1:
                    RESPAWN.send(index, time=remaining_time)
                else:
                    RESPAWNS.send(index, time=remaining_time)
            else:
                self.delay(0, self.spawn)

#=================================
# Weapons Restrict
#=================================
class MyWeaponRestrictionHandler(WeaponRestrictionHandler):
    def on_player_purchasing_weapon(self, player, weapon_name):
        if player.is_bot():
            return False

    def on_player_bumping_weapon(self, player, weapon_name):
        if player.is_bot() and weapon_name != 'knife':
            return False

weapon_restriction_handler = MyWeaponRestrictionHandler()
#=================================
# Functions
#=================================
def end_round():
    Entity.find_or_create('info_map_parameters').fire_win_condition(9)

@Repeat
def hint_panel():
    title = get_day_name()
    humans = alive_humans()
    for player in PlayerIter('human'):
        index = player.index
        player = ZRPlayer(index)

        target = player.hurted_zombie
        if target is None:
            HINT_INFO.send(index, title=title, day=day, max_day=max_day, humans=humans, zombies=zombies)
        else:
            try:
                target_player = Player(index_from_userid(target))
                if not target_player.dead:
                    HINT_INFO_BOT.send(index, title=title, day=day, max_day=max_day, humans=humans, zombies=zombies, name=target_player.name, health=target_player.health)
                else:
                    target = None
            except ValueError:
                target = None

@Repeat
def background():
    BACKGROUND_SOUND.stop()
    BACKGROUND_SOUND.play()

def change_random_map():
    maps = []
    for all_maps in MAP_LIST:
        map_name = all_maps.split('.')[0]
        if engine_server.is_map_valid(map_name):
            maps.append(map_name)

    if len(maps):
        next_map = choice(maps)
        NEXT_MAP_SELECTED.send(prefix=prefix, map_name=next_map, RED=RED, BRIGHT_GREEN=BRIGHT_GREEN)
        MAP_CHANGE.send()
        Delay(3, queue_command_string, (f'changelevel {next_map}',))
    else:
        NO_NEXT_MAP_FOUND.send(prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED)

def cancel_freeze_delay():
    global freeze_delay, flash_delay, god_delay
    frozen_delay = freeze_delay
    unfreeze = flash_delay
    godmode_delay = god_delay

    if frozen_delay is not None and frozen_delay.running:
        frozen_delay.cancel()

    if unfreeze is not None and unfreeze.running:
        unfreeze.cancel()

    if godmode_delay is not None and godmode_delay.running:
        godmode_delay.cancel()

def get_max_day():
    count = 0
    for i in _settings['zr']:
        count += 1
    return count

def bots_count():
    return len(PlayerIter('bot'))

def alive_humans():
    return len(PlayerIter(['alive', 'human']))

def remove_idle_weapons():
    for weapons in filter(lambda x: x.owner_handle in [-1, 0], WeaponIter()):
        weapons.remove()

def get_day_name():
    try:
        return _settings['zr'][f'{day}']['name']
    except KeyError:
        return ''

def get_zombie_model():
    models = []
    for i in _settings['zr'][f'{day}']['model']:
        models.append(i.split(','))
    if len(models) is 0:
        return _settings['zr'][f'{day}']['model']
    else:
        return choice(models)

def get_zombie_kill_amount():
    return int(_settings['zr'][f'{day}']['zombies'])

def get_zombies_health():
    return int(_settings['zr'][f'{day}']['health'])

def get_zombies_speed():
    return float(_settings['zr'][f'{day}']['speed'])

def move_day_forward():
    global day
    day += 1
    if day > max_day:
        day = 1
        if bool(enable_random_map):
            change_random_map()

def reset_color(player):
    player.color = Color(255, 255, 255)
#=================================
# Commands
#=================================
@ServerCommand('zr_set_day')
def zr_set_day_command(args):
    global day
    if not len(args) == 2:
        return

    try:
        amount = int(args[1])
    except ValueError:
        return
    day = amount
    print(f'[ZR]: Day was set to {amount}')

if bool(enable_market):
    @SayCommand(['market', '!market', '/market'])
    def market_command(command, index, team_only):
        player = Player(index)
        if player.dead:
            return MARKET_ALIVE.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED)

        if not player.team == 3:
            return MARKET_TEAM.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED)

        main_market_menu.send(index)
        return False
#=================================
# Events & Hooks
#=================================
server = find_binary('server')

if PLATFORM == 'windows':
    identifier = b'\x55\x8B\xEC\x83\xEC\x2A\x8B\x45\x0C\x53\x56\x57\x33\xF6'
else:
    identifier = '_ZN12CCSGameRules14TerminateRoundEfi'

terminate_round = server[identifier].make_function(Convention.THISCALL, [DataType.POINTER, DataType.FLOAT, DataType.INT], DataType.VOID)

@PreHook(terminate_round)
def pre_terminate_round(args):
    reason = args[2]
    global zombies
    if zombies > 0 and alive_humans() > 0 and not reason in [9, 15, 16]:
        return 0

if bool(enable_freeze_flash):
    @EntityPreHook(EntityCondition.is_human_player, 'deafen')
    @EntityPreHook(EntityCondition.is_human_player, 'blind')
    def _pre_blind(stack_data):
	    return False

if bool(enable_smokegrenade_light):
    @OnEntityCreated
    def on_entity_created(entity):
        if entity.classname != 'env_particlesmokegrenade':
            return
        entity.remove()

@OnPlayerRunCommand
def on_player_run_command(player, user_cmd):
    global freeze_delay
    if player.dead:
        return
    if not player.is_bot():
        return

    frozen_delay = freeze_delay
    if frozen_delay is not None and frozen_delay.running:
        user_cmd.buttons &= ~PlayerButtons.ATTACK
        user_cmd.buttons &= ~PlayerButtons.ATTACK2

@OnLevelShutdown
def shutdown():
    global day, zombies
    day = 1
    zombies = 0

    cancel_freeze_delay()
    del joined[:]

@Event('player_team')
def player_team(args):
    userid = args.get_int('userid')
    team = args.get_int('team')
    player = ZRPlayer.from_userid(userid)
    steamid = player.steamid
    if team == 3:
        if steamid in joined:
            player.delay(0, player.respawn_human, (0, 30))
        else:
            player.delay(0, player.respawn_human, (0, 10))
            joined.append(steamid)

@Event('round_start')
def round_start(args):
    global zombies, max_day

    max_day = get_max_day()
    zombies = get_zombie_kill_amount()
    cancel_freeze_delay()

    for player in PlayerIter('all'):
        player.client_command('r_screenoverlay 0')
        ZRPlayer(player.index).hurted_zombie = None

    entity = Entity.find('light_dynamic')
    if entity is not None:
        entity.call_input('Kill')

    remove_idle_weapons()

    if zombies >= 20:
        amount = 20
    else:
        amount = zombies

    queue_command_string(f'bot_quota {amount}')

    if bool(enable_background_sound):
        BACKGROUND_SOUND.stop()
        BACKGROUND_SOUND.play()
        background.start(60)

    if bool(enable_server_name):
        _server_name.set_string('')
        _server_name.set_string(f'{server_name.get_string()}' + f'Day: {day}/{max_day}')

@Event('round_end')
def round_end(args):
    global day
    reason = args.get_int('reason')
    if reason in [15, 16]:
        day = 1

    if bool(enable_background_sound):
        BACKGROUND_SOUND.stop()
        background.stop()

@Event('round_freeze_end')
def round_freeze_end(args):
    global freeze_delay, god_delay
    for bot in PlayerIter('bot'):
        bot.godmode = True
        bot.set_stuck(True)
        freeze_delay = bot.delay(10, bot.set_stuck, (False,))
        god_delay = bot.delay(10, bot.set_godmode, (False,))

@Event('player_hurt')
def player_hurt(args):
    userid = args.get_int('userid')
    attacker = args.get_int('attacker')
    if attacker > 0:
        if not userid == attacker:
            ZRPlayer.from_userid(attacker).hurted_zombie = userid
            if args.get_string('weapon') == 'hegrenade' and enable_fire_grenade.get_int() is 1:
                Player.from_userid(userid).ignite_lifetime(10)

if bool(enable_freeze_flash):
    @Event('flashbang_detonate')
    def flashbang_detonate(args):
        global flash_delay, freeze_delay

        if freeze_delay is not None and freeze_delay.running:
            return

        radius = freeze_radius.get_int()
        duration = freeze_duration.get_float()

        x = args.get_float('x')
        y = args.get_float('y')
        z = args.get_float('z')

        for zombie in filter(lambda x: x.stuck == False, PlayerIter(['alive', 'bot'])):
            distance = zombie.origin.get_distance(Vector(x, y, z))
            if distance <= radius:
                zombie.stuck = True
                zombie.color = Color(0, 255, 255)
                zombie.delay(duration, zombie.set_stuck, (False,))
                zombie.delay(duration, reset_color, (zombie,))
                ICE_SOUND.origin = zombie.origin
                ICE_SOUND.play()

if bool(enable_smokegrenade_light):
    @Event('smokegrenade_detonate')
    def smokegrenade_detonate(args):
        x 	= args.get_float('x')
        y 	= args.get_float('y')
        z 	= args.get_float('z')
        ent = Entity.create("light_dynamic")
        ent.inner_cone = 0
        ent.cone = 100
        ent.brightness = 1
        ent.spotlight_radius = 300
        ent.pitch = 200
        ent.style = 5
        ent._light = Color(255, 255, 0, 255)
        ent.distance = 300
        ent.spawn()
        ent.origin = Vector(x,y,z)
        ent.call_input('TurnOn')

@Event('player_spawn')
def player_spawn(args):
    userid = args.get_int('userid')   
    player = Player.from_userid(userid)
    if player.dead:
        return

    index = player.index

    player.noblock = True
    player.cash = spawn_money.get_int()

    if player.is_bot():
        player.health = get_zombies_health()
        player.set_model(Model(get_zombie_model()))
        player.speed = get_zombies_speed()

    if bool(enable_market):
        MARKET.send(index, prefix=prefix, RED=RED, BRIGHT_GREEN=BRIGHT_GREEN, GREEN=GREEN)
    GAMEPLAY.send(index, prefix=prefix)

@Event('player_death')
def player_death(args):
    global zombies
    userid = args.get_int('userid')
    attacker = args.get_int('attacker')
    player = ZRPlayer.from_userid(userid)

    if player.is_bot():
        zombies -= 1
        if zombies >= bots_count():
           if alive_humans() > 0:
                player.delay(0, player.spawn)

        if attacker > 0:
            a_player = ZRPlayer.from_userid(attacker)
            if a_player.hurted_zombie == userid:
                a_player.hurted_zombie = None

        if zombies == 0:
            move_day_forward()
            for player in PlayerIter('human'):
                player.client_command('r_screenoverlay overlays/zr/humans_win.vmt')
    else:
        if zombies > 0 and alive_humans() > 0:
            player.respawn_human(0, 30)

    if alive_humans() == 0:
        for player in PlayerIter('human'):
            player.client_command('r_screenoverlay overlays/zr/zombies_win.vmt')

    remove_idle_weapons()

#=================================
# Menus Callbacks
#=================================
def main_market_menu_callback(menu, index, option):
    choice = option.value
    if choice == 'primaries':
        primary_market_menu.send(index)
    elif choice == 'secondaries':
        secondary_market_menu.send(index)

def primary_market_menu_callback(menu, index, option):
    choice = option.value

    player = Player(index)
    cash = player.cash

    price = choice.cost
    primary = player.primary
    weapon_basename = choice.basename

    if not player.team == 3:
        return PURCHASE_TEAM.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)

    if player.dead:
        return PURCHASE_ALIVE.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)

    if cash >= price:
        player.cash = cash - price

        if primary is not None:
            primary.remove()

        player.give_named_item(choice)
        PURCHASED_SUCCESFULLY.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename, price=price)

    else:
        return PURCHASE_AFFORD.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)

def secondary_market_menu_callback(menu, index, option):
    choice = option.value

    player = Player(index)
    cash = player.cash

    price = choice.cost
    secondary = player.secondary
    weapon_basename = choice.basename

    if not player.team == 3:
        return PURCHASE_TEAM.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)

    if player.dead:
        return PURCHASE_ALIVE.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)

    if cash >= price:
        player.cash = cash - price

        if secondary is not None:
            secondary.remove()

        player.give_named_item(choice)
        PURCHASED_SUCCESFULLY.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename, price=price)

    else:
        return PURCHASE_AFFORD.send(index, prefix=prefix, GREEN=GREEN, BRIGHT_GREEN=BRIGHT_GREEN, RED=RED, weapon=weapon_basename)
#=================================
# Menus Build Callbacks
#=================================
def build_primary_market_menu(menu, index):
	menu.clear()
	player = Player(index)
	cash = player.cash
	alive_status = player.dead

	for primary in WeaponClassIter('primary'):
		price = primary.cost
		afford = cash >= price and not alive_status
		menu.append(PagedOption(f'{primary.basename} {price}$', primary, afford, afford))

def build_secondary_market_menu(menu, index):
	menu.clear()
	player = Player(index)
	cash = player.cash
	alive_status = player.dead

	for secondary in WeaponClassIter('pistol'):
		price = secondary.cost
		afford = cash >= price and not alive_status
		menu.append(PagedOption(f'{secondary.basename} {price}$', secondary, afford, afford))

#=================================
# Global Menus
#=================================
main_market_menu = SimpleMenu()
main_market_menu.append(Text('Market'))
main_market_menu.append(Text(' '))
main_market_menu.append(SimpleOption(1, 'Purchase Primaries', 'primaries'))
main_market_menu.append(SimpleOption(2, 'Purchase Secondaries', 'secondaries'))
main_market_menu.append(Text(' '))
main_market_menu.append(SimpleOption(0, 'Close', None))
main_market_menu.select_callback = main_market_menu_callback

primary_market_menu = PagedMenu(title='Select primary to purchase')
primary_market_menu.build_callback = build_primary_market_menu
primary_market_menu.select_callback = primary_market_menu_callback

secondary_market_menu = PagedMenu(title='Select secondary to purchase')
secondary_market_menu.build_callback = build_secondary_market_menu
secondary_market_menu.select_callback = secondary_market_menu_callback

import discord
import os
import random
import json
import asyncio
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv
from discord.ext import commands, tasks
from keep_alive import keep_alive

# Config
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 950063903394631710
LEADERBOARD_IMAGE_URL = "https://media.discordapp.net/attachments/588488751974449163/1388201522348691466/sddefault.png?ex=68601eea&is=685ecd6a&hm=559323f7e27a0f53c67751d524d554c79e4a09f99ce3408f50cf50085ae993a4&=&format=webp&quality=lossless"
LEADERBOARD_CHANNEL_ID = 1369760540695592980
LOYALTY_WEIGHT = 0.2

ROLE_CONFIG = {
    "MRBAB": {
        "id": 1388197495133306941,
        "weight": 1,
        "points": 10
    },
    "Rajel": {
        "id": 1369759295947935806,
        "weight": 250,
        "points": 2
    },
    "NPC": {
        "id": 1369759970043760640,
        "weight": 250,
        "points": 1
    },
    "Gay": {
        "id": 1369760023135391866,
        "weight": 250,
        "points": -1
    },
    "Na9ch": {
        "id": 1369759897771577354,
        "weight": 249,
        "points": -2
    }
}

COOLDOWN_HOURS = 24
COOLDOWN_FILE = "cooldowns.json"
PLAYER_STATS_FILE = "player_stats.json"
ROLE_EXPIRATIONS_FILE = "role_expirations.json"


# --- DATA HANDLING FUNCTIONS ---
def load_cooldowns():
    try:
        with open(COOLDOWN_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, 'w') as f:
        json.dump(cooldowns, f, indent=4)


def load_player_stats():
    try:
        with open(PLAYER_STATS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_player_stats(stats):
    with open(PLAYER_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=4)


def load_role_expirations():
    try:
        with open(ROLE_EXPIRATIONS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_role_expirations(expirations):
    with open(ROLE_EXPIRATIONS_FILE, 'w') as f:
        json.dump(expirations, f, indent=4)


# --- BOT SETUP ---
class MyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(RandomRoleView())
        print("Persistent view added.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        daily_board_post.start()
        check_role_expirations.start()
        print("Bot is ready and listening for commands.")
        print("Daily leaderboard task is running.")
        print("Role expiration checker is running.")


bot = MyBot()


# --- THE PERSISTENT BUTTON VIEW ---
class RandomRoleView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Try Your Luck!",
                       style=discord.ButtonStyle.danger,
                       emoji="🎰",
                       custom_id="random_role_button")
    async def button_callback(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        try:
            user = interaction.user
            user_id_str = str(user.id)

            cooldowns = load_cooldowns()

            if user_id_str in cooldowns:
                last_press_time = datetime.fromisoformat(
                    cooldowns[user_id_str])
                cooldown_end_time = last_press_time + timedelta(
                    hours=COOLDOWN_HOURS)
                if datetime.now() < cooldown_end_time:
                    remaining_time = cooldown_end_time - datetime.now()
                    hours, remainder = divmod(remaining_time.total_seconds(),
                                              3600)
                    minutes, _ = divmod(remainder, 60)
                    await interaction.response.send_message(
                        f"You're on cooldown! Please wait another **{int(hours)} hours and {int(minutes)} minutes**.",
                        ephemeral=True)
                    return

            await interaction.response.defer(ephemeral=False, thinking=True)
            all_random_role_ids = {role['id'] for role in ROLE_CONFIG.values()}
            roles_to_remove = [
                role for role in user.roles if role.id in all_random_role_ids
            ]
            if roles_to_remove:
                await user.remove_roles(*roles_to_remove,
                                        reason="Daily role swap")

            role_names = list(ROLE_CONFIG.keys())
            role_weights = [role['weight'] for role in ROLE_CONFIG.values()]
            chosen_role_name = random.choices(role_names,
                                              weights=role_weights,
                                              k=1)[0]
            chosen_role_id = ROLE_CONFIG[chosen_role_name]['id']
            role_to_add = interaction.guild.get_role(chosen_role_id)

            if role_to_add:
                await user.add_roles(role_to_add,
                                     reason="Daily random role assignment")

                cooldowns[user_id_str] = datetime.now().isoformat()
                save_cooldowns(cooldowns)

                stats = load_player_stats()
                user_data = stats.get(
                    user_id_str, {
                        "display_name": user.display_name,
                        "roles": {
                            name: 0
                            for name in ROLE_CONFIG.keys()
                        }
                    })
                user_data["display_name"] = user.display_name
                if chosen_role_name not in user_data["roles"]:
                    user_data["roles"][chosen_role_name] = 0
                user_data["roles"][chosen_role_name] += 1
                stats[user_id_str] = user_data
                save_player_stats(stats)

                expirations = load_role_expirations()
                expiration_time = datetime.now() + timedelta(
                    hours=COOLDOWN_HOURS)
                expirations[user_id_str] = {
                    "role_id": chosen_role_id,
                    "expiration_time": expiration_time.isoformat()
                }
                save_role_expirations(expirations)

                await interaction.followup.send(
                    f"Rigelha {user.mention}! Rak **{role_to_add.name}** lyoum!"
                )
            else:
                await interaction.followup.send(
                    f"Error: Could not find the role with ID {chosen_role_id}. Please contact an admin.",
                    ephemeral=True)

        except discord.errors.NotFound as e:
            if e.code == 10062:
                print(
                    "Ignoring an 'Unknown Interaction' error. This is normal after a bot restart."
                )
            else:
                raise e


# --- BACKGROUND TASKS ---
@tasks.loop(minutes=1)
async def check_role_expirations():
    await bot.wait_until_ready()
    now = datetime.now()
    expirations = load_role_expirations()
    expired_users = []
    for user_id, data in expirations.items():
        expire_time = datetime.fromisoformat(data["expiration_time"])
        if now >= expire_time:
            guild = bot.get_guild(GUILD_ID)
            if not guild: continue
            member = guild.get_member(int(user_id))
            role_to_remove = guild.get_role(data["role_id"])
            if member and role_to_remove:
                try:
                    await member.remove_roles(
                        role_to_remove, reason="Role expired after 24 hours")
                    print(
                        f"Removed role {role_to_remove.name} from {member.display_name} as it expired."
                    )
                except discord.Forbidden:
                    print(
                        f"ERROR: Missing permissions to remove role {role_to_remove.name} from {member.display_name}."
                    )
                except discord.HTTPException as e:
                    print(f"ERROR: Failed to remove role. {e}")
            expired_users.append(user_id)
    if expired_users:
        for user_id in expired_users:
            if user_id in expirations:
                del expirations[user_id]
        save_role_expirations(expirations)


@tasks.loop(hours=24)
async def daily_board_post():
    guild, channel = bot.get_guild(GUILD_ID), bot.get_channel(
        LEADERBOARD_CHANNEL_ID)
    if channel and guild:
        await channel.send(
            f"**Leaderboard Update for {datetime.now().strftime('%Y-%m-%d')}**",
            embed=generate_leaderboard_embed(guild))
    else:
        print(
            f"Error: Could not find channel ({LEADERBOARD_CHANNEL_ID}) or guild ({GUILD_ID})."
        )


@daily_board_post.before_loop
async def before_daily_post():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    target_time = time(0, 0, 0, tzinfo=timezone.utc)
    next_run = datetime.combine(now.date(), target_time)
    if now.time() > target_time: next_run += timedelta(days=1)
    seconds_until_midnight = (next_run - now).total_seconds()
    print(
        f"Daily board will be posted in {seconds_until_midnight/3600:.2f} hours."
    )
    await asyncio.sleep(seconds_until_midnight)


# --- LEADERBOARD AND OTHER COMMANDS ---
def generate_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    stats = load_player_stats()
    embed = discord.Embed(title="Gambling Core Leaderboard",
                          color=discord.Color.gold())
    embed.set_thumbnail(url=LEADERBOARD_IMAGE_URL)
    if not stats:
        embed.description = "The season has just begun! Be the first to try your luck."
        return embed
    sorted_players = sorted(
        stats.items(),
        key=lambda item:
        (sum(item[1]['roles'].get(r, 0) * ROLE_CONFIG[r]['points']
             for r in item[1]['roles'])) +
        (sum(item[1]['roles'].values()) * LOYALTY_WEIGHT),
        reverse=True)
    leaderboard_string = ""
    rank = 1
    for user_id, data in sorted_players:
        name, roles = data['display_name'], data['roles']
        total_plays, total_points = sum(roles.values()), sum(
            count * ROLE_CONFIG[role_name]['points']
            for role_name, count in roles.items())
        final_score = total_points + (total_plays * LOYALTY_WEIGHT)
        jackpot, rajel, na9ch, npc, gay = roles.get("MRBAB", 0), roles.get(
            "Rajel", 0), roles.get("Na9ch",
                                   0), roles.get("NPC",
                                                 0), roles.get("Gay", 0)
        leaderboard_string += (
            f"**{rank}. {name}** — **{final_score:.2f} Score** (Points: {total_points})\n> Plays: {total_plays} | MRBAB Rolls: {jackpot}\n> `Rajel : {rajel}` `Na9ch: {na9ch}` `NPC: {npc}` `Gay : {gay}`\n--------------------\n"
        )
        rank += 1
        if len(leaderboard_string) > 3800:
            leaderboard_string += "...and more!"
            break
    embed.description = leaderboard_string
    embed.set_footer(
        text=
        f"Ranking uses a Loyalty Score (Total Points + {LOYALTY_WEIGHT} per play)"
    )
    return embed


@bot.command(name="board")
async def board(ctx: commands.Context):
    await ctx.send(embed=generate_leaderboard_embed(ctx.guild))


@bot.command(name="rigl")
async def setup_role_panel(ctx: commands.Context):
    await ctx.send(
        "## 🎲 Are you read ?\n\n"
        "Once every 24 hours, the wheel of destiny turns... Dare to click the button below and surrender your identity to the whims of chance. Your current role will be cast into oblivion — replaced by a new, unpredictable fate. Will you rise as a legend… or fall into obscurity? Only one way to find out.",
        view=RandomRoleView())


@setup_role_panel.error
async def setup_panel_error(ctx: commands.Context,
                            error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "This should not happen, but you do not have permission to use this command.",
            delete_after=10)
        await ctx.message.delete()


# --- RUN THE BOT ---
#keep_alive()
bot.run(TOKEN)
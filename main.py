import discord
import os
import random
import json
import asyncio
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv
from discord.ext import commands, tasks

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 950063903394631710
LEADERBOARD_IMAGE_URL = "https://media.discordapp.net/attachments/588488751974449163/1388201522348691466/sddefault.png?ex=68601eea&is=685ecd6a&hm=559323f7e27a0f53c67751d524d554c79e4a09f99ce3408f50cf50085ae993a4&=&format=webp&quality=lossless"
LEADERBOARD_CHANNEL_ID = 1369760540695592980
### ADDED: The "fairness" knob for the ranking system.
# A higher number makes each play more valuable. 0.1 is a good starting point.
LOYALTY_WEIGHT = 0.2

### UPDATED: Role config with new JACKPOT role, re-balanced weights, and corrected points.
ROLE_CONFIG = {
    # Role Name:          { id: role_id,               weight: chance, points: value }
    "JACKPOT":            {"id": 1388197495133306941, "weight": 1,    "points": 10},  # 1 in 1000 chance (0.1%)
    "rak rajel lyom":     {"id": 1369759295947935806, "weight": 250,  "points": 2},   # Approx 25% chance
    "NPC":                {"id": 1369759970043760640, "weight": 250,  "points": 1},   # Approx 25% chance
    "nta gay lyom":       {"id": 1369760023135391866, "weight": 250,  "points": -1},  # Approx 25% chance
    "nta na9ch lyom":     {"id": 1369759897771577354, "weight": 249,  "points": -2}   # Approx 24.9% chance
}
# Weights now total 1000 (1 + 250 + 250 + 250 + 249)

COOLDOWN_HOURS = 24
COOLDOWN_FILE = "cooldowns.json"
PLAYER_STATS_FILE = "player_stats.json"

# --- DATA HANDLING FUNCTIONS (No changes here) ---
def load_cooldowns():
    try:
        with open(COOLDOWN_FILE, 'r') as f: return json.load(f)
    except FileNotFoundError: return {}

def save_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, 'w') as f: json.dump(cooldowns, f, indent=4)

def load_player_stats():
    try:
        with open(PLAYER_STATS_FILE, 'r') as f: return json.load(f)
    except FileNotFoundError: return {}

def save_player_stats(stats):
    with open(PLAYER_STATS_FILE, 'w') as f: json.dump(stats, f, indent=4)

# --- BOT SETUP (No changes here) ---
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
        print("Bot is ready and listening for commands.")
        print("Daily leaderboard task is running.")

bot = MyBot()

# --- THE PERSISTENT BUTTON VIEW (No changes here) ---
class RandomRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.cooldowns = load_cooldowns()

    @discord.ui.button(label="Try Your Luck!", style=discord.ButtonStyle.danger, emoji="🎰", custom_id="random_role_button")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        user_id_str = str(user.id)

        if user_id_str in self.cooldowns:
            last_press_time = datetime.fromisoformat(self.cooldowns[user_id_str])
            cooldown_end_time = last_press_time + timedelta(hours=COOLDOWN_HOURS)
            if datetime.now() < cooldown_end_time:
                remaining_time = cooldown_end_time - datetime.now()
                hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                await interaction.response.send_message(
                    f"You're on cooldown! Please wait another **{int(hours)} hours and {int(minutes)} minutes**.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=False, thinking=True)
        all_random_role_ids = {role['id'] for role in ROLE_CONFIG.values()}
        roles_to_remove = [role for role in user.roles if role.id in all_random_role_ids]
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason="Daily role swap")

        role_names = list(ROLE_CONFIG.keys())
        role_weights = [role['weight'] for role in ROLE_CONFIG.values()]
        chosen_role_name = random.choices(role_names, weights=role_weights, k=1)[0]
        chosen_role_id = ROLE_CONFIG[chosen_role_name]['id']
        role_to_add = interaction.guild.get_role(chosen_role_id)

        if role_to_add:
            await user.add_roles(role_to_add, reason="Daily random role assignment")
            self.cooldowns[user_id_str] = datetime.now().isoformat()
            save_cooldowns(self.cooldowns)
            
            stats = load_player_stats()
            user_data = stats.get(user_id_str, {
                "display_name": user.display_name,
                "roles": {name: 0 for name in ROLE_CONFIG.keys()}
            })
            user_data["display_name"] = user.display_name
            # Ensure the new role key exists if the player is old
            if chosen_role_name not in user_data["roles"]:
                user_data["roles"][chosen_role_name] = 0
            user_data["roles"][chosen_role_name] += 1
            stats[user_id_str] = user_data
            save_player_stats(stats)

            await interaction.followup.send(f"Rigelha {user.mention}! You've received the **{role_to_add.name}** today!")
        else:
            await interaction.followup.send(f"Error: Could not find the role with ID {chosen_role_id}. Please contact an admin.", ephemeral=True)

### --- UPDATED: LEADERBOARD GENERATION LOGIC --- ###
def generate_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    """Calculates all stats and formats them into a Discord Embed using a Loyalty Score."""
    stats = load_player_stats()
    embed = discord.Embed(title="Gambling Core Leaderboard", color=discord.Color.gold())
    embed.set_thumbnail(url=LEADERBOARD_IMAGE_URL)

    if not stats:
        embed.description = "The season has just begun! Be the first to try your luck."
        return embed

    ### --- CORE RANKING CHANGE --- ###
    # We now sort players based on the new "Final Score" formula.
    sorted_players = sorted(
        stats.items(),
        key=lambda item: 
            (sum(item[1]['roles'].get(r, 0) * ROLE_CONFIG[r]['points'] for r in item[1]['roles'])) + 
            (sum(item[1]['roles'].values()) * LOYALTY_WEIGHT),
        reverse=True
    )

    leaderboard_string = ""
    rank = 1
    for user_id, data in sorted_players:
        name = data['display_name']
        roles = data['roles']
        
        # Calculations
        total_plays = sum(roles.values())
        total_points = sum(count * ROLE_CONFIG[role_name]['points'] for role_name, count in roles.items())
        
        # Calculate the final score used for ranking
        final_score = total_points + (total_plays * LOYALTY_WEIGHT)

        # Other stats for display
        jackpot = roles.get("JACKPOT", 0)
        rak_rajel = roles.get("rak rajel lyom", 0)
        nta_na9ch = roles.get("nta na9ch lyom", 0)
        npc = roles.get("NPC", 0)
        nta_gay = roles.get("nta gay lyom", 0)

        # Append each player's stats to the description string
        leaderboard_string += (
            ### --- UPDATED LINE TO SHOW THE NEW FINAL SCORE --- ###
            f"**{rank}. {name}** — **{final_score:.2f} Score** (Points: {total_points})\n"
            
            f"> Plays: {total_plays} | Jackpot Rolls: {jackpot}\n"
            f"> `rak rajel: {rak_rajel}` `nta na9ch: {nta_na9ch}` `NPC: {npc}` `nta gay: {nta_gay}`\n"
            "--------------------\n"
        )
        rank += 1
        if len(leaderboard_string) > 3800:
            leaderboard_string += "...and more!"
            break
            
    embed.description = leaderboard_string
    embed.set_footer(text=f"Ranking uses a Loyalty Score (Total Points + {LOYALTY_WEIGHT} per play)")
    return embed

@bot.command(name="board", help="Displays the server's role gambling leaderboard.")
async def board(ctx: commands.Context):
    leaderboard_embed = generate_leaderboard_embed(ctx.guild)
    await ctx.send(embed=leaderboard_embed)

@tasks.loop(hours=24)
async def daily_board_post():
    guild = bot.get_guild(GUILD_ID)
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel and guild:
        leaderboard_embed = generate_leaderboard_embed(guild)
        await channel.send(f"**Leaderboard Update for {datetime.now().strftime('%Y-%m-%d')}**", embed=leaderboard_embed)
    else:
        print(f"Error: Could not find channel ({LEADERBOARD_CHANNEL_ID}) or guild ({GUILD_ID}).")

@daily_board_post.before_loop
async def before_daily_post():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    target_time = time(0, 0, 0, tzinfo=timezone.utc)
    next_run = datetime.combine(now.date(), target_time)
    if now.time() > target_time:
        next_run += timedelta(days=1)
    
    seconds_until_midnight = (next_run - now).total_seconds()
    print(f"Daily board will be posted in {seconds_until_midnight/3600:.2f} hours.")
    await asyncio.sleep(seconds_until_midnight)

@bot.command(name="rigl", help="Posts the random role button panel. Admin only.")
@commands.has_permissions(administrator=True)
async def setup_role_panel(ctx: commands.Context):
    view = RandomRoleView()
    await ctx.send(
        "## 🎲 Face the Unknown — Let Fate Decide!!\n\n"
        " Once every 24 hours, the wheel of destiny turns..."
        " Dare to click the button below and surrender your identity to the whims of chance."
        " Your current role will be cast into oblivion — replaced by a new, unpredictable fate."
        " Will you rise as a legend… or fall into obscurity?"
        " Only one way to find out. ",
        view=view
    )
    await ctx.message.delete()

@setup_role_panel.error
async def setup_panel_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.", delete_after=10)
        await ctx.message.delete()

# --- RUN THE BOT ---
bot.run(TOKEN)
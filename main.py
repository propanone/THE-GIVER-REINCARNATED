import discord
import os
import random
import json
import asyncio
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv
from discord.ext import commands, tasks
from keep_alive import keep_alive
import sys

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 950063903394631710
LEADERBOARD_IMAGE_URL = "https://media.discordapp.net/attachments/588488751974449163/1388201522348691466/sddefault.png?ex=68601eea&is=685ecd6a&hm=559323f7e27a0f53c67751d524d554c79e4a09f99ce3408f50cf50085ae993a4&=&format=webp&quality=lossless"
LEADERBOARD_CHANNEL_ID = 1369760540695592980
LOYALTY_WEIGHT = 0.2
SHUTDOWN_ALLOWED_USERS = [569924649417441291]

ROLE_CONFIG = {
    "MRBAB": {"id": 1388197495133306941, "weight": 1, "points": 10},
    "Rajel": {"id": 1369759295947935806, "weight": 250, "points": 2},
    "NPC": {"id": 1369759970043760640, "weight": 250, "points": 1},
    "Gay": {"id": 1369760023135391866, "weight": 250, "points": -1},
    "Na9ch": {"id": 1369759897771577354, "weight": 249, "points": -2}
}

MRBAB_WEIGHT_INCREASE = 0.01 
COOLDOWN_HOURS = 20

COOLDOWN_FILE = "cooldowns.json"
PLAYER_STATS_FILE = "player_stats.json"
ROLE_EXPIRATIONS_FILE = "role_expirations.json"
WEEKLY_STATS_FILE = "weekly_stats.json"
GAME_STATE_FILE = "game_state.json"

# --- DATA HANDLING FUNCTIONS ---
def load_data(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            if not content: return [] if 'expirations' in file_path else {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return [] if 'expirations' in file_path else {}

def save_data(data, file_path):
    with open(file_path, 'w') as f: json.dump(data, f, indent=4)

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
        weekly_highlights_post.start()
        print("Bot is ready and listening for commands.")
        print("Daily leaderboard task is running.")
        print("Role expiration checker is running.")
        print("Weekly highlights task is running.")

bot = MyBot()

# --- THE PERSISTENT BUTTON VIEW ---
class RandomRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Try Your Luck!", style=discord.ButtonStyle.danger, emoji="🎰", custom_id="random_role_button")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.user
            user_id_str = str(user.id)
            cooldowns = load_data(COOLDOWN_FILE)
            if user_id_str in cooldowns:
                last_press_time = datetime.fromisoformat(cooldowns[user_id_str])
                cooldown_end_time = last_press_time + timedelta(hours=COOLDOWN_HOURS)
                if datetime.now() < cooldown_end_time:
                    remaining_time = cooldown_end_time - datetime.now()
                    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    await interaction.response.send_message(f"You're on cooldown! Please wait another **{int(hours)} hours and {int(minutes)} minutes**.", ephemeral=True)
                    return
            
            await interaction.response.defer(ephemeral=False, thinking=True)
            
            standard_role_ids = {v['id'] for k, v in ROLE_CONFIG.items() if k != "MRBAB"}
            roles_to_remove = [role for role in user.roles if role.id in standard_role_ids]
            if roles_to_remove: await user.remove_roles(*roles_to_remove, reason="Daily role swap")

            game_state = load_data(GAME_STATE_FILE)
            plays_since_jackpot = game_state.get("plays_since_jackpot", 0)
            current_mrbab_weight = ROLE_CONFIG["MRBAB"]["weight"] + (plays_since_jackpot * MRBAB_WEIGHT_INCREASE)
            weight_to_remove = current_mrbab_weight - ROLE_CONFIG["MRBAB"]["weight"]
            other_roles = [r for r in ROLE_CONFIG if r != "MRBAB"]
            loss_per_role = weight_to_remove / len(other_roles) if other_roles else 0
            dynamic_weights = {}
            for role_name, config in ROLE_CONFIG.items():
                if role_name == "MRBAB": dynamic_weights[role_name] = current_mrbab_weight
                else: dynamic_weights[role_name] = max(1, config["weight"] - loss_per_role)
            role_names, final_weights = list(dynamic_weights.keys()), [int(w) for w in dynamic_weights.values()]
            chosen_role_name = random.choices(role_names, weights=final_weights, k=1)[0]
            chosen_role_id = ROLE_CONFIG[chosen_role_name]['id']
            role_to_add = interaction.guild.get_role(chosen_role_id)
            
            if role_to_add:
                await user.add_roles(role_to_add, reason="Daily random role assignment")
                cooldowns[user_id_str] = datetime.now().isoformat()
                save_data(cooldowns, COOLDOWN_FILE)
                
                def update_stats(stats_file):
                    stats = load_data(stats_file)
                    user_data = stats.get(user_id_str, {"display_name": user.display_name, "roles": {name: 0 for name in ROLE_CONFIG.keys()}})
                    user_data["display_name"] = user.display_name
                    if chosen_role_name not in user_data["roles"]: user_data["roles"][chosen_role_name] = 0
                    user_data["roles"][chosen_role_name] += 1
                    stats[user_id_str] = user_data
                    save_data(stats, stats_file)
                update_stats(PLAYER_STATS_FILE)
                update_stats(WEEKLY_STATS_FILE)
                
                expirations = load_data(ROLE_EXPIRATIONS_FILE)
                if chosen_role_name == "MRBAB": expiration_time = datetime.now() + timedelta(days=7)
                else: expiration_time = datetime.now() + timedelta(hours=COOLDOWN_HOURS)
                new_expiration_record = {"user_id": user_id_str, "role_id": chosen_role_id, "expiration_time": expiration_time.isoformat()}
                expirations.append(new_expiration_record)
                save_data(expirations, ROLE_EXPIRATIONS_FILE)
                
                if chosen_role_name == "MRBAB":
                    game_state["plays_since_jackpot"] = 0
                    jackpot_embed = discord.Embed(title="🎰🎰🎰  J A C K P O T  🎰🎰🎰", description=f"The long wait is over! After **{plays_since_jackpot + 1}** community plays, the jackpot has been hit!", color=discord.Color.gold())
                    jackpot_embed.add_field(name="Congratulations to our new MRBAB!", value=f"**{user.mention}**", inline=False)
                    jackpot_embed.set_thumbnail(url="https://img.freepik.com/premium-photo/golden-jackpot-slot-machine-exciting-casino-win_1160504-6235.jpg")
                    jackpot_embed.set_footer(text="This winner is promised a 1 dollar gift from Moh4t")
                    await interaction.followup.send("@everyone", embed=jackpot_embed)
                else:
                    game_state["plays_since_jackpot"] = plays_since_jackpot + 1
                    await interaction.followup.send(f"Rigelha {user.mention}! Rak **{role_to_add.name}** lyoum!")
                
                save_data(game_state, GAME_STATE_FILE)
            else:
                await interaction.followup.send(f"Error: Could not find the role with ID {chosen_role_id}. Please contact an admin.", ephemeral=True)
        except discord.errors.NotFound as e:
            if e.code == 10062: print("Ignoring an 'Unknown Interaction' error. This is normal after a bot restart.")
            else: raise e

# --- BACKGROUND TASKS ---
@tasks.loop(minutes=1)
async def check_role_expirations():
    await bot.wait_until_ready()
    now = datetime.now()
    all_expirations = load_data(ROLE_EXPIRATIONS_FILE)
    still_active_expirations = []
    if not all_expirations: return
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    for record in all_expirations:
        expire_time = datetime.fromisoformat(record["expiration_time"])
        if now >= expire_time:
            user_id, role_id = int(record["user_id"]), int(record["role_id"])
            member = guild.get_member(user_id)
            role_to_remove = guild.get_role(role_id)
            if member and role_to_remove:
                try:
                    await member.remove_roles(role_to_remove, reason="Gambling role expired")
                    print(f"Removed expired role {role_to_remove.name} from {member.display_name}.")
                except discord.Forbidden: print(f"ERROR: Missing permissions to remove role {role_to_remove.name} from {member.display_name}.")
                except discord.HTTPException as e: print(f"ERROR: Failed to remove role. {e}")
        else:
            still_active_expirations.append(record)
    save_data(still_active_expirations, ROLE_EXPIRATIONS_FILE)

@tasks.loop(hours=24)
async def daily_board_post():
    guild, channel = bot.get_guild(GUILD_ID), bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel and guild: await channel.send(f"**Leaderboard Update for {datetime.now().strftime('%Y-%m-%d')}**", embed=generate_leaderboard_embed(guild))
    else: print(f"Error: Could not find channel ({LEADERBOARD_CHANNEL_ID}) or guild ({GUILD_ID}).")

@daily_board_post.before_loop
async def before_daily_post():
    await bot.wait_until_ready()
    now, target_time = datetime.now(timezone.utc), time(0, 0, 0, tzinfo=timezone.utc)
    next_run = datetime.combine(now.date(), target_time)
    if now.time() > target_time: next_run += timedelta(days=1)
    await asyncio.sleep((next_run - now).total_seconds())
    print(f"Daily board will be posted in {(next_run - now).total_seconds()/3600:.2f} hours.")

def generate_weekly_highlights_embed():
    weekly_stats = load_data(WEEKLY_STATS_FILE)
    if not weekly_stats: return None
    embed = discord.Embed(title=" Weekly Gambling Report ", description="Here are the highlights from the past week!", color=discord.Color.blue())
    embed.set_thumbnail(url="https://neurosciencenews.com/files/2020/02/slot-machine-vision-sound-neurosciennewws-public.jpg")
    def get_weekly_winner(role_name):
        max_count, winners = 0, []
        for user_id, data in weekly_stats.items():
            count = data["roles"].get(role_name, 0)
            if count > max_count: max_count, winners = count, [user_id]
            elif count == max_count and count > 0: winners.append(user_id)
        if not winners: return "No one! A quiet week."
        return f'{", ".join([f"<@{uid}>" for uid in winners])} (with **{max_count}** rolls)'
    embed.add_field(name="👑 MRBAB of the Week", value=get_weekly_winner("MRBAB"), inline=False)
    embed.add_field(name="💪 Rajel of the Week", value=get_weekly_winner("Rajel"), inline=False)
    embed.add_field(name="🤖 NPC of the Week", value=get_weekly_winner("NPC"), inline=False)
    embed.add_field(name="🏳️‍🌈 Gay of the Week", value=get_weekly_winner("Gay"), inline=False)
    embed.add_field(name="🤡 Na9ch of the Week", value=get_weekly_winner("Na9ch"), inline=False)
    return embed

@tasks.loop(hours=168)
async def weekly_highlights_post():
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel: print("Weekly highlights: Could not find leaderboard channel."); return
    embed = generate_weekly_highlights_embed()
    if embed:
        await channel.send(embed=embed)
        save_data({}, WEEKLY_STATS_FILE)
        print("Weekly highlights posted and weekly stats have been reset.")
    else:
        print("Weekly highlights: No weekly stats to process. Skipping.")

@weekly_highlights_post.before_loop
async def before_weekly_highlights():
    await bot.wait_until_ready()
    # Schedule for Friday at 8 PM Algeria Time (19:00 UTC)
    now = datetime.now(timezone.utc)
    # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    target_weekday = 4 
    target_time = time(19, 0, 0, tzinfo=timezone.utc)
    
    days_until_target = (target_weekday - now.weekday() + 7) % 7
    next_run_date = now.date() + timedelta(days=days_until_target)
    
    next_run_datetime = datetime.combine(next_run_date, target_time)
    if now > next_run_datetime:
        next_run_datetime += timedelta(weeks=1) # Use weeks=1 for clarity

    sleep_seconds = (next_run_datetime - now).total_seconds()
    print(f"Weekly highlights will be posted in {sleep_seconds / 3600:.2f} hours.")
    await asyncio.sleep(sleep_seconds)

def generate_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    stats = load_data(PLAYER_STATS_FILE)
    embed = discord.Embed(title="Gambling Core Leaderboard", color=discord.Color.gold())
    embed.set_thumbnail(url=LEADERBOARD_IMAGE_URL)
    if not stats:
        embed.description = "The season has just begun! Be the first to try your luck."
        return embed
    sorted_players = sorted(stats.items(), key=lambda item: (sum(item[1]['roles'].get(r, 0) * ROLE_CONFIG[r]['points'] for r in item[1]['roles'])) + (sum(item[1]['roles'].values()) * LOYALTY_WEIGHT), reverse=True)
    leaderboard_string = ""; rank = 1
    for user_id, data in sorted_players:
        name, roles = data['display_name'], data['roles']
        total_plays, total_points = sum(roles.values()), sum(count * ROLE_CONFIG[role_name]['points'] for role_name, count in roles.items())
        final_score = total_points + (total_plays * LOYALTY_WEIGHT)
        jackpot, rajel, na9ch, npc, gay = roles.get("MRBAB", 0), roles.get("Rajel", 0), roles.get("Na9ch", 0), roles.get("NPC", 0), roles.get("Gay", 0)
        leaderboard_string += (f"**{rank}. {name}** — **{final_score:.2f} Score** (Points: {total_points})\n> Plays: {total_plays} | MRBAB Rolls: {jackpot}\n> `Rajel : {rajel}` `Na9ch: {na9ch}` `NPC: {npc}` `Gay : {gay}`\n--------------------\n")
        rank += 1
        if len(leaderboard_string) > 3800: leaderboard_string += "...and more!"; break
    embed.description = leaderboard_string
    embed.set_footer(text=f"Ranking uses a Loyalty Score (Total Points + {LOYALTY_WEIGHT} per play)")
    return embed

@bot.command(name="board")
async def board(ctx: commands.Context):
    await ctx.send(embed=generate_leaderboard_embed(ctx.guild))

@bot.command(name="rigl")
async def setup_role_panel(ctx: commands.Context):
    await ctx.send("## 🎲 Are you ready ?\n\n", view=RandomRoleView())

@setup_role_panel.error
async def setup_panel_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions): await ctx.send("This should not happen, but you do not have permission to use this command.", delete_after=10); await ctx.message.delete()

# --- NEW COMMAND ---
@bot.command(name="chances", help="Shows the current gambling odds for each role.")
async def chances(ctx: commands.Context):
    """Calculates and displays the current probability of rolling each role."""
    try:
        # 1. Load the game state to get the pity counter
        game_state = load_data(GAME_STATE_FILE)
        plays_since_jackpot = game_state.get("plays_since_jackpot", 0)

        # 2. Replicate the dynamic weight calculation from the button press
        current_mrbab_weight = ROLE_CONFIG["MRBAB"]["weight"] + (plays_since_jackpot * MRBAB_WEIGHT_INCREASE)
        weight_to_remove = current_mrbab_weight - ROLE_CONFIG["MRBAB"]["weight"]
        other_roles = [r for r in ROLE_CONFIG if r != "MRBAB"]
        loss_per_role = weight_to_remove / len(other_roles) if other_roles else 0

        dynamic_weights = {}
        for role_name, config in ROLE_CONFIG.items():
            if role_name == "MRBAB":
                dynamic_weights[role_name] = current_mrbab_weight
            else:
                # Ensure weight doesn't go below a minimum (e.g., 1)
                dynamic_weights[role_name] = max(1, config["weight"] - loss_per_role)

        # 3. Calculate total weight and percentages
        total_weight = sum(dynamic_weights.values())
        
        chances_data = []
        for role_name, weight in dynamic_weights.items():
            percentage = (weight / total_weight) * 100
            chances_data.append({"name": role_name, "weight": weight, "percentage": percentage})
        
        # Sort by percentage for readability
        chances_data.sort(key=lambda x: x['percentage'], reverse=True)

        # 4. Create the embed
        embed = discord.Embed(
            title="🎰 Current Gambling Odds",
            description="Here are the real-time probabilities for your next roll. The chance for **MRBAB** increases with every community play that isn't a jackpot!",
            color=discord.Color.dark_purple()
        )
        
        # 5. Format and add the data to the embed
        chances_string = ""
        for item in chances_data:
            role_name = item['name']
            weight = item['weight']
            percentage = item['percentage']
            # Using 4 decimal places for percentages can be helpful for very low chances
            chances_string += f"**{role_name}**: `{percentage:.4f}%` (Weight: {weight:.2f})\n"
        
        embed.add_field(name="Role Probabilities", value=chances_string, inline=False)
        
        embed.set_footer(text=f"The jackpot 'pity system' is currently at +{plays_since_jackpot} plays.")
        
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Error in !chances command: {e}")
        await ctx.send("An error occurred while calculating the chances. Please check the bot logs.")
# --- END NEW COMMAND ---

def is_allowed_user():
    def predicate(ctx: commands.Context) -> bool: return ctx.author.id in SHUTDOWN_ALLOWED_USERS
    return commands.check(predicate)

@bot.command(name="weeklyreport", help="Manually generates the weekly highlights report without resetting stats.")
@is_allowed_user()
async def weeklyreport(ctx: commands.Context):
    embed = generate_weekly_highlights_embed()
    if embed: await ctx.send("Here is the current weekly report preview:", embed=embed)
    else: await ctx.send("There is no data for the current week to report on.")

@weeklyreport.error
async def weeklyreport_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure): await ctx.send("You do not have permission to use this command.")

@bot.command(name="shutdown", help="Shuts down the bot. Allowed users only.")
@is_allowed_user()
async def shutdown(ctx: commands.Context):
    await ctx.send("Bot is shutting down..."); print("Shutdown command received. Closing bot connection...")
    await bot.close(); print("Bot connection closed. Exiting process.")
    sys.exit()

@shutdown.error
async def shutdown_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure): await ctx.send("You do not have permission to use this command.")

# --- RUN THE BOT ---
keep_alive()
bot.run(TOKEN)